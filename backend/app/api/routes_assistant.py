"""
Assistant chat endpoint — the primary demo surface.

Response deliberately separates:
  - redacted_message: what was sent to the LLM (entity-type labels, no PII)
  - detected_pii_types: which PII types were found (safe to log/display)
  - response: the AI's answer
  - trace: full agent execution path (Explainable AI)

The original user message is NOT echoed back — the frontend already has it.
The client shows [original message] vs [redacted_message] side-by-side.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import TokenData
from app.db import get_db
from app.ledger.outbox import write_decision_with_intent

router = APIRouter(prefix="/assistant", tags=["assistant"])

REQUEST_TYPES = {"FRAUD_CHECK", "IDENTITY", "COMPLIANCE", "CO_LENDING", "GENERAL_QUERY", "ASSISTANT"}


class AssistantRequest(BaseModel):
    message: str
    user_id: str | None = None
    account_id: str | None = None
    request_type: str = "ASSISTANT"
    request_id: str | None = None


class AssistantResponse(BaseModel):
    request_id: str
    decision_id: str | None
    # PII-safe fields — these are returned to the client
    redacted_message: str           # what was actually sent to the LLM
    detected_pii_types: list[str]   # entity types found (not raw values)
    response: str                   # AI answer
    outcome: str
    confidence: float | None
    trace: list[str]
    memory_hit: bool
    model_used: str | None
    # Circular compliance gate result (None if gate unavailable)
    circular_result: dict | None = None


@router.post("/chat", response_model=AssistantResponse)
async def chat(
    payload: AssistantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    gate = request.app.state.redaction_gate
    adapter = request.app.state.bank_adapter
    valkey = request.app.state.valkey
    qdrant = request.app.state.qdrant_client

    request_id = payload.request_id or str(uuid.uuid4())
    request_type = payload.request_type if payload.request_type in REQUEST_TYPES else "ASSISTANT"

    # ── Redact the user message (step 1: happens before ANYTHING else) ───────
    redaction = gate.redact(payload.message)

    # ── Build initial graph state ─────────────────────────────────────────────
    from app.agents.state import VeritasState

    initial_state = VeritasState(
        request_id=request_id,
        request_type=request_type,
        raw_input=payload.message,
        redacted_input=redaction.text,
        entity_map=redaction.entity_map,
        user_id=payload.user_id,
        account_id=payload.account_id,
        trace=[
            f"redaction_gate: detected=[{', '.join(redaction.detected_types)}] "
            f"entities_masked={len(redaction.mapping)}"
        ],
        extra_context={},
        memory_hit=False,
        rule_fired=False,
    )

    # ── Run the graph ──────────────────────────────────────────────────────────
    graph = request.app.state.agent_graph
    final_state = await graph.ainvoke(initial_state)

    outcome = final_state.get("final_outcome") or "NEEDS_REVIEW"
    confidence = final_state.get("final_confidence")
    llm_response = final_state.get("llm_response") or _build_rule_response(final_state)
    model_used = final_state.get("model_used")
    memory_hit = final_state.get("memory_hit", False)
    trace = final_state.get("trace", [])
    decision_id = final_state.get("decision_id")

    return AssistantResponse(
        request_id=request_id,
        decision_id=decision_id,
        redacted_message=redaction.text,
        detected_pii_types=redaction.detected_types,
        response=llm_response,
        outcome=outcome,
        confidence=confidence,
        trace=trace,
        memory_hit=memory_hit,
        model_used=model_used,
        circular_result=final_state.get("circular_result"),
    )


def _build_rule_response(state: dict) -> str:
    """
    When a hard rule fires and no LLM is called, synthesise a concise
    human-readable response from the structured agent results.
    """
    compliance = state.get("compliance_result") or {}
    identity = state.get("identity_result") or {}
    fraud = state.get("fraud_result") or {}

    outcome = state.get("final_outcome", "NEEDS_REVIEW")
    rule_id = compliance.get("rule_id") or identity.get("rule_id") or fraud.get("rule_id")
    risk_tier = identity.get("details", {}).get("risk_tier", "")
    kyc = identity.get("details", {}).get("kyc_status", "")

    if outcome == "APPROVED":
        return (
            f"Your request has been approved. "
            + (f"Policy rule {rule_id} confirmed eligibility. " if rule_id else "")
            + (f"KYC status: {kyc}. Risk tier: {risk_tier}." if kyc else "")
        )
    elif outcome == "REJECTED":
        # Check if circular gate blocked it first
        circ = state.get("circular_result") or {}
        if circ.get("phase") in ("hard_rule", "llm") and not circ.get("valid"):
            violated = ", ".join(circ.get("violated_rules", [])) or "circular policy"
            return (
                f"This request was blocked by the IDBI Circular Compliance Gate. "
                f"Reason: {circ.get('reason', 'Policy violation')} "
                f"(violated: {violated}). Please refer to the relevant policy circular."
            )
        reason = compliance.get("details", {}).get("reason") or fraud.get("details", {}).get("note") or "Policy requirements not met."
        return f"Your request could not be approved at this time. {reason} Rule: {rule_id or 'N/A'}."
    elif outcome == "FLAGGED":
        fraud_score = fraud.get("details", {}).get("fraud_score", "N/A")
        return f"This request has been flagged for review (fraud score: {fraud_score}). A bank representative will contact you."
    else:
        return "Your request is under review. A representative will follow up with you shortly."
