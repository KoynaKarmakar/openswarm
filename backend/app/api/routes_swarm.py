"""
OpenSwarm decision endpoint — the swarm-orchestrated counterpart to
/assistant/chat.

POST /swarm/decide runs the request through the four-agent swarm
(Guardrail → Knowledge → Identity&Fraud → Auditor) instead of the static
LangGraph pipeline. The response exposes the dynamic handoff path and the
0-100 confidence score so the OpenSwarm dashboard can visualise the run.

PII contract is unchanged: the raw message is redacted by the Guardrail agent
before anything else sees it; only redacted text and non-PII results are
returned.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import TokenData
from app.db import get_db
from app.swarm.context import SwarmContext
from app.swarm.orchestrator import build_swarm

router = APIRouter(prefix="/swarm", tags=["swarm"])

REQUEST_TYPES = {"FRAUD_CHECK", "IDENTITY", "COMPLIANCE", "CO_LENDING", "GENERAL_QUERY", "ASSISTANT"}


class SwarmRequest(BaseModel):
    message: str
    user_id: str | None = None
    account_id: str | None = None
    request_type: str = "ASSISTANT"
    request_id: str | None = None
    extra_context: dict = {}
    # Optional presented Google Verifiable Credential (W3C VC 2.0).
    verifiable_credential: dict | None = None
    # Optional Aadhaar auth (UIDAI Auth 2.5-shaped, DEMO by default). The raw
    # number is used only for verification and is never echoed, logged, or sent
    # to the LLM — only a masked reference appears in the response.
    aadhaar: str | None = None
    aadhaar_name: str | None = None
    aadhaar_yob: str | None = None
    aadhaar_otp: str | None = None


class SwarmResponse(BaseModel):
    request_id: str
    decision_id: str | None
    outcome: str
    confidence: float | None
    confidence_score: float | None       # 0-100, printed by the Auditor
    redacted_message: str
    detected_pii_types: list[str]
    response: str | None                 # grounded LLM answer, if any
    handoff_path: list[str]              # which agents ran, in order
    trace: list[str]
    vc_verification: dict | None = None       # Google VC connector result, if presented
    aadhaar_verification: dict | None = None  # UIDAI-shaped result (masked UID only)


@router.post("/decide", response_model=SwarmResponse)
async def decide(
    payload: SwarmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    request_id = payload.request_id or str(uuid.uuid4())
    request_type = payload.request_type if payload.request_type in REQUEST_TYPES else "ASSISTANT"

    extra_context = dict(payload.extra_context or {})
    if payload.verifiable_credential:
        extra_context["verifiable_credential"] = payload.verifiable_credential
    if payload.aadhaar:
        extra_context["aadhaar"] = payload.aadhaar
        if payload.aadhaar_name:
            extra_context["aadhaar_name"] = payload.aadhaar_name
        if payload.aadhaar_yob:
            extra_context["aadhaar_yob"] = payload.aadhaar_yob
        if payload.aadhaar_otp:
            extra_context["aadhaar_otp"] = payload.aadhaar_otp

    ctx = SwarmContext(
        request_id=request_id,
        request_type=request_type,
        raw_input=payload.message,
        user_id=payload.user_id,
        account_id=payload.account_id,
        extra_context=extra_context,
    )

    swarm = build_swarm(
        gate=request.app.state.redaction_gate,
        adapter=request.app.state.bank_adapter,
        qdrant=request.app.state.qdrant_client,
        db=db,
        circular_gate=getattr(request.app.state, "circular_gate", None),
    )
    result = await swarm.run(ctx)

    entity_map = result.get("entity_map") or {}
    identity = result.get("identity_result") or {}
    details = identity.get("details") or {}
    vc = details.get("vc_verification")
    aadhaar = details.get("aadhaar_auth")

    return SwarmResponse(
        request_id=request_id,
        decision_id=result.get("decision_id"),
        outcome=result.get("final_outcome") or "NEEDS_REVIEW",
        confidence=result.get("final_confidence"),
        confidence_score=result.get("confidence_score"),
        redacted_message=result.get("redacted_input") or "",
        detected_pii_types=sorted(set(entity_map.values())),
        response=result.get("llm_response"),
        handoff_path=result.handoff_path,
        trace=result.trace,
        vc_verification=vc,
        aadhaar_verification=aadhaar,
    )
