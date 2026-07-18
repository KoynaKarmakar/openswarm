"""
VERITAS graph state — the single dict that flows through every node.

Design rules:
- raw_input is set once at entry; never modified after redaction_gate runs.
- redacted_input + entity_map are the ONLY values that flow to LLM or cache.
- mapping (token→original) is NEVER stored in state — it stays scoped to the
  redaction_gate node's local frame and is discarded after the node returns.
- trace accumulates a list of strings so every downstream node can append
  without overwriting earlier entries.
"""

from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict
import operator


def _merge_lists(a: list, b: list) -> list:
    return a + b


class AgentResult(TypedDict, total=False):
    outcome: str          # APPROVED / REJECTED / FLAGGED / NEEDS_REVIEW
    confidence: float
    rule_id: str | None   # which hard rule fired, if any
    details: dict         # agent-specific details (never raw PII)


class VeritasState(TypedDict, total=False):
    # ── Input ───────────────────────────────────────────────────────────────
    request_id: str
    request_type: str         # FRAUD_CHECK | IDENTITY | COMPLIANCE | ASSISTANT
    raw_input: str            # user's original text — never sent to LLM
    user_id: str | None
    account_id: str | None
    transaction_id: str | None
    extra_context: dict       # structured fields from the request body

    # ── After redaction gate ─────────────────────────────────────────────────
    redacted_input: str       # entity-type labels replacing PII
    entity_map: dict          # {label: entity_type} — safe to log, no raw values

    # ── Circular compliance gate (runs before all agents) ───────────────────
    circular_result: dict | None      # CircularValidationResult.to_dict()

    # ── Agent results (populated by each agent node) ─────────────────────────
    identity_result: AgentResult | None
    fraud_result: AgentResult | None
    compliance_result: AgentResult | None
    policy_result: AgentResult | None

    # ── Routing ──────────────────────────────────────────────────────────────
    memory_hit: bool          # True if Valkey returned a cached decision
    rule_fired: bool          # True if a hard policy rule resolved the request
    cache_key: str | None     # the key that hit (for tracing)

    # ── LLM call ─────────────────────────────────────────────────────────────
    llm_response: str | None
    model_used: str | None

    # ── Final decision ────────────────────────────────────────────────────────
    final_outcome: str | None         # APPROVED | REJECTED | FLAGGED | NEEDS_REVIEW
    final_confidence: float | None
    decision_id: str | None           # UUID of the persisted Decision row

    # ── Explainability trace (append-only across nodes) ──────────────────────
    # Annotated with operator.add so LangGraph merges lists instead of replacing
    trace: Annotated[list[str], operator.add]

    # ── Error handling ────────────────────────────────────────────────────────
    error: str | None


def route_after_memory_check(state: "VeritasState") -> str:
    """
    Pure routing function — no imports beyond this module.
    Used by the graph conditional edge AND importable in tests without
    pulling in sqlalchemy / redis.
    """
    if state.get("memory_hit") or state.get("rule_fired"):
        return "decision_coordinator"
    return "llm_call"
