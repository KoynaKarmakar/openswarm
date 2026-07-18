import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import TokenData
from app.db import get_db
from app.ledger.outbox import write_decision_with_intent

router = APIRouter(prefix="/identity", tags=["identity"])


class IdentityRequest(BaseModel):
    customer_id: str
    request_id: str | None = None


class IdentityResponse(BaseModel):
    request_id: str
    decision_id: str | None
    outcome: str
    confidence: float | None
    kyc_status: str
    risk_tier: str
    co_lending_eligible: bool
    did_credential: dict
    trace: list[str]


@router.post("/verify", response_model=IdentityResponse)
async def verify_identity(
    payload: IdentityRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    adapter = request.app.state.bank_adapter
    gate = request.app.state.redaction_gate

    request_id = payload.request_id or str(uuid.uuid4())

    from app.agents.identity_agent import identity_node
    from app.agents.state import VeritasState

    state = VeritasState(
        request_id=request_id,
        request_type="IDENTITY",
        user_id=payload.customer_id,
        raw_input=f"Identity verification request for customer {payload.customer_id}",
        trace=[],
        extra_context={},
    )

    update = await identity_node(state, adapter)
    result = update.get("identity_result", {})
    details = result.get("details", {})

    try:
        async with db.begin():
            decision = await write_decision_with_intent(
                db,
                request_id=request_id,
                decision_type="IDENTITY",
                outcome=result.get("outcome", "NEEDS_REVIEW"),
                confidence=result.get("confidence"),
                trace=update.get("trace", []),
                redacted_context=None,
            )
        decision_id = str(decision.id)
    except Exception:
        decision_id = None

    return IdentityResponse(
        request_id=request_id,
        decision_id=decision_id,
        outcome=result.get("outcome", "NEEDS_REVIEW"),
        confidence=result.get("confidence"),
        kyc_status=details.get("kyc_status", "UNKNOWN"),
        risk_tier=details.get("risk_tier", "D"),
        co_lending_eligible=details.get("co_lending_eligible", False),
        did_credential=details.get("did_credential", {}),
        trace=update.get("trace", []),
    )


class EligibilityResponse(BaseModel):
    request_id: str
    decision_id: str | None
    kyc_status: str
    risk_tier: str
    did_credential: dict
    eligibility_outcome: str
    eligibility_rule_id: str | None
    eligibility_confidence: float | None
    trace: list[str]


@router.post("/co-lending-eligibility", response_model=EligibilityResponse)
async def co_lending_eligibility(
    payload: IdentityRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Chains identity_node → compliance_node's CLM-00X rule evaluation — the
    two are otherwise disconnected (/identity/verify never runs the CLM
    rules). Drives the Co-Lending Eligibility guided flow.
    """
    adapter = request.app.state.bank_adapter
    request_id = payload.request_id or str(uuid.uuid4())

    from app.agents.identity_agent import identity_node
    from app.agents.compliance_agent import compliance_node
    from app.agents.state import VeritasState

    state = VeritasState(
        request_id=request_id,
        request_type="CO_LENDING",
        user_id=payload.customer_id,
        raw_input=f"Co-lending eligibility check for customer {payload.customer_id}",
        trace=[],
        extra_context={},
    )

    identity_update = await identity_node(state, adapter)
    identity_result = identity_update.get("identity_result", {})
    details = identity_result.get("details", {})

    state["identity_result"] = identity_result
    state["trace"] = identity_update.get("trace", [])

    compliance_update = await compliance_node(state)
    compliance_result = compliance_update.get("compliance_result", {})

    trace = identity_update.get("trace", []) + compliance_update.get("trace", [])

    try:
        async with db.begin():
            decision = await write_decision_with_intent(
                db,
                request_id=request_id,
                decision_type="CO_LENDING_ELIGIBILITY",
                outcome=compliance_result.get("outcome", "NEEDS_REVIEW"),
                confidence=compliance_result.get("confidence"),
                trace=trace,
                redacted_context=None,
            )
        decision_id = str(decision.id)
    except Exception:
        decision_id = None

    return EligibilityResponse(
        request_id=request_id,
        decision_id=decision_id,
        kyc_status=details.get("kyc_status", "UNKNOWN"),
        risk_tier=details.get("risk_tier", "D"),
        did_credential=details.get("did_credential", {}),
        eligibility_outcome=compliance_result.get("outcome", "NEEDS_REVIEW"),
        eligibility_rule_id=compliance_result.get("rule_id"),
        eligibility_confidence=compliance_result.get("confidence"),
        trace=trace,
    )
