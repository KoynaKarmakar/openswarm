"""
VERITAS Multi-Agent LangGraph Orchestrator.

Graph topology:
    START
      ↓
    redaction_gate      — redact raw_input, populate redacted_input + entity_map
      ↓
    circular_gate       — validate against IDBI policy circulars (hard rules → LLM)
      ↓ (conditional)
    ├─ [NON_COMPLIANT]  → decision_coordinator  (blocked)
    └─ [COMPLIANT/AMBIGUOUS]
      ↓
    identity_agent      — KYC check via BankAdapter
      ↓
    fraud_agent         — fraud score check via BankAdapter
      ↓
    compliance_agent    — hard policy rules (CLM, UEBT, KYC)
      ↓
    policy_agent        — RAG retrieval for soft policy questions
      ↓
    memory_check        — Valkey cache lookup OR hard rule already resolved?
      ↓ (conditional)
    ├─ [cache_hit OR rule_fired] → decision_coordinator
    └─ [needs LLM]               → llm_call_node → decision_coordinator
      ↓
    decision_coordinator — write Decision + OutboxIntent atomically
      ↓
    END

Every path reaches decision_coordinator → no branch skips the audit trail.
The `trace` field on the returned state IS the Explainable AI output.
"""

from __future__ import annotations

import logging
import uuid
from functools import partial
from typing import Callable

import redis.asyncio as aioredis
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import BankAdapter
from app.agents.circular_gate_node import make_circular_gate_node, route_after_circular_gate
from app.agents.compliance_agent import compliance_node
from app.agents.fraud_agent import fraud_node
from app.agents.identity_agent import identity_node
from app.agents.policy_agent import policy_node
from app.agents.state import VeritasState, route_after_memory_check
from app.ledger.outbox import write_decision_with_intent
from app.llm.router import chat_completion
from app.redaction.gate import RedactionGate

logger = logging.getLogger("veritas.graph")

_CACHE_TTL_SECONDS = 300  # 5 minutes


# ── Node implementations ──────────────────────────────────────────────────────

def make_redaction_node(gate: RedactionGate) -> Callable:
    async def redaction_gate_node(state: VeritasState) -> dict:
        raw = state.get("raw_input", "")
        result = gate.redact(raw)
        return {
            "redacted_input": result.text,
            "entity_map": result.entity_map,
            # result.mapping (token→original) is intentionally NOT stored in state
            "trace": [
                f"redaction_gate: detected=[{', '.join(result.detected_types)}] "
                f"entities_masked={len(result.mapping)}"
            ],
        }
    return redaction_gate_node


def make_identity_node(adapter: BankAdapter) -> Callable:
    async def _node(state: VeritasState) -> dict:
        return await identity_node(state, adapter)
    return _node


def make_fraud_node(adapter: BankAdapter) -> Callable:
    async def _node(state: VeritasState) -> dict:
        return await fraud_node(state, adapter)
    return _node


async def _memory_check_node(state: VeritasState, valkey: aioredis.Redis) -> dict:
    """
    Check Valkey for a cached decision for this exact request fingerprint.
    Also checks if a hard rule already fired (compliance_agent sets rule_fired=True).
    """
    if state.get("rule_fired"):
        return {
            "memory_hit": False,
            "trace": ["memory_check: hard rule fired — skipping cache, routing to decision_coordinator"],
        }

    cache_key = f"veritas:decision:{state.get('request_type')}:{state.get('user_id')}:{state.get('account_id')}"
    try:
        cached = await valkey.get(cache_key)
    except Exception:
        cached = None

    if cached:
        import json as _json
        return {
            "memory_hit": True,
            "cache_key": cache_key,
            "cached_response": _json.loads(cached),
            "trace": [f"memory_check: CACHE HIT key={cache_key}"],
        }

    return {
        "memory_hit": False,
        "cache_key": cache_key,
        "trace": [f"memory_check: cache miss key={cache_key} — routing to LLM"],
    }


def make_memory_check_node(valkey: aioredis.Redis) -> Callable:
    async def _node(state: VeritasState) -> dict:
        return await _memory_check_node(state, valkey)
    return _node


async def _llm_call_node(state: VeritasState) -> dict:
    """
    Call the LLM with the REDACTED context only.
    Builds a system prompt that includes agent summaries (no PII).
    """
    system_prompt = (
        "You are VERITAS, an AI banking compliance assistant. "
        "You receive pre-analysed, PII-redacted banking context and must provide "
        "a concise, compliant decision recommendation with reasoning. "
        "Never ask for or repeat PII. Be factual and cite relevant policy."
    )

    identity = state.get("identity_result") or {}
    fraud = state.get("fraud_result") or {}
    compliance = state.get("compliance_result") or {}
    policy = state.get("policy_result") or {}
    policy_context = policy.get("details", {}).get("policy_context", "")

    context_parts = [
        f"Request type: {state.get('request_type', 'UNKNOWN')}",
        f"Redacted user input: {state.get('redacted_input', '')}",
        f"Identity check: {identity.get('outcome')} (KYC={identity.get('details', {}).get('kyc_status')}, "
        f"risk_tier={identity.get('details', {}).get('risk_tier')})",
        f"Fraud check: {fraud.get('outcome')} (score={fraud.get('details', {}).get('fraud_score', 'N/A')})",
        f"Compliance check: {compliance.get('outcome')} (rule={compliance.get('rule_id')})",
    ]

    if policy_context:
        context_parts.append(f"\nRelevant policy sections:\n{policy_context}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(context_parts)},
    ]

    try:
        response = await chat_completion(messages, temperature=0.1, max_tokens=512)
        return {
            "llm_response": response.content,
            "model_used": response.model_used,
            "trace": [f"llm_call: model={response.model_used} output_tokens={response.output_tokens}"],
        }
    except RuntimeError as exc:
        logger.error("LLM call failed: %s", exc)
        return {
            "llm_response": None,
            "model_used": None,
            "error": str(exc),
            "trace": [f"llm_call: FAILED — {exc}"],
        }


def make_decision_coordinator(db: AsyncSession) -> Callable:
    async def _node(state: VeritasState) -> dict:
        """
        Determine the final outcome and write Decision + OutboxIntent atomically.
        This node is always reached — no branch skips it.
        """
        # Resolve final outcome: fraud overrides identity overrides compliance
        fraud = state.get("fraud_result") or {}
        identity = state.get("identity_result") or {}
        compliance = state.get("compliance_result") or {}
        cached = state.get("cached_response") or {}

        if state.get("memory_hit") and cached:
            outcome = cached.get("outcome", "NEEDS_REVIEW")
            confidence = cached.get("confidence", 0.5)
            source = "cache"
        elif fraud.get("outcome") == "REJECTED":
            outcome, confidence, source = "REJECTED", fraud.get("confidence", 0.9), "fraud_agent"
        elif fraud.get("outcome") == "FLAGGED":
            outcome, confidence, source = "FLAGGED", fraud.get("confidence", 0.7), "fraud_agent"
        elif identity.get("outcome") == "REJECTED":
            outcome, confidence, source = "REJECTED", identity.get("confidence", 0.9), "identity_agent"
        elif compliance.get("outcome") in ("APPROVED_FAST_TRACK", "APPROVED_STANDARD", "APPROVED"):
            outcome = "APPROVED"
            confidence = compliance.get("confidence", 0.9)
            source = "compliance_agent"
        elif compliance.get("outcome") == "REJECTED":
            outcome, confidence, source = "REJECTED", compliance.get("confidence", 0.95), "compliance_agent"
        elif state.get("llm_response"):
            # LLM path — parse outcome from response (Step 3 will add structured output)
            outcome, confidence, source = "APPROVED", 0.7, "llm"
        else:
            outcome, confidence, source = "NEEDS_REVIEW", 0.5, "fallback"

        request_id = state.get("request_id") or str(uuid.uuid4())
        full_trace = state.get("trace", []) + [f"decision_coordinator: outcome={outcome} via={source}"]

        try:
            async with db.begin():
                decision = await write_decision_with_intent(
                    db,
                    request_id=request_id,
                    decision_type=state.get("request_type", "UNKNOWN"),
                    outcome=outcome,
                    confidence=confidence,
                    trace=full_trace,
                    redacted_context=state.get("redacted_input"),
                )
            decision_id = str(decision.id)
        except Exception as exc:
            logger.exception("Failed to write decision to DB")
            decision_id = None
            full_trace.append(f"decision_coordinator: DB write FAILED — {exc}")

        return {
            "final_outcome": outcome,
            "final_confidence": confidence,
            "decision_id": decision_id,
            "trace": [f"decision_coordinator: outcome={outcome} decision_id={decision_id}"],
        }

    return _node


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(
    gate: RedactionGate,
    adapter: BankAdapter,
    valkey: aioredis.Redis,
    db: AsyncSession,
    qdrant=None,
    circular_gate=None,
) -> StateGraph:
    """
    Build and compile the VERITAS StateGraph.
    Dependencies are injected here — nodes are pure async functions.
    """
    builder = StateGraph(VeritasState)

    builder.add_node("redaction_gate", make_redaction_node(gate))
    builder.add_node("circular_gate", make_circular_gate_node(circular_gate))
    builder.add_node("identity_agent", make_identity_node(adapter))
    builder.add_node("fraud_agent", make_fraud_node(adapter))
    builder.add_node("compliance_agent", compliance_node)

    from functools import partial
    _policy_with_qdrant = partial(policy_node, qdrant_client=qdrant)
    builder.add_node("policy_agent", _policy_with_qdrant)
    builder.add_node("memory_check", make_memory_check_node(valkey))
    builder.add_node("llm_call", _llm_call_node)
    builder.add_node("decision_coordinator", make_decision_coordinator(db))

    # redaction → circular gate → (conditional) identity or decision_coordinator
    builder.add_edge(START, "redaction_gate")
    builder.add_edge("redaction_gate", "circular_gate")
    builder.add_conditional_edges(
        "circular_gate",
        route_after_circular_gate,
        {
            "identity_agent": "identity_agent",
            "decision_coordinator": "decision_coordinator",
        },
    )

    builder.add_edge("identity_agent", "fraud_agent")
    builder.add_edge("fraud_agent", "compliance_agent")
    builder.add_edge("compliance_agent", "policy_agent")
    builder.add_edge("policy_agent", "memory_check")

    builder.add_conditional_edges(
        "memory_check",
        route_after_memory_check,
        {
            "decision_coordinator": "decision_coordinator",
            "llm_call": "llm_call",
        },
    )

    builder.add_edge("llm_call", "decision_coordinator")
    builder.add_edge("decision_coordinator", END)

    return builder.compile()
