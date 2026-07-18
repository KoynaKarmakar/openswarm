import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import TokenData
from app.db import get_db
from app.ledger.outbox import write_decision_with_intent
from app.models.case import Case, CaseOverride, CaseStatus, OverrideAction

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseSummary(BaseModel):
    id: str
    account_id: str
    customer_id: str | None
    case_type: str
    status: str
    fraud_score: float | None
    rule_id: str | None
    liability_tier: str
    compensation_percent: float
    sla_deadline: str
    created_at: str


class CaseDetail(CaseSummary):
    source_request_id: str
    decision_id: str | None
    trace: list[str]


class OverrideRequest(BaseModel):
    action: str  # ACCEPT | REJECT
    reason: str


class OverrideResponse(BaseModel):
    case_id: str
    status: str
    decision_id: str | None


def _summary(c: Case) -> CaseSummary:
    return CaseSummary(
        id=str(c.id),
        account_id=c.account_id,
        customer_id=c.customer_id,
        case_type=c.case_type.value,
        status=c.status.value,
        fraud_score=c.fraud_score,
        rule_id=c.rule_id,
        liability_tier=c.liability_tier,
        compensation_percent=c.compensation_percent,
        sla_deadline=c.sla_deadline.isoformat(),
        created_at=c.created_at.isoformat(),
    )


@router.get("", response_model=list[CaseSummary])
async def list_cases(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    query = select(Case).order_by(Case.sla_deadline.asc())
    if status_filter:
        try:
            query = query.where(Case.status == CaseStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status_filter}")
    result = await db.execute(query)
    cases = result.scalars().all()
    return [_summary(c) for c in cases]


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    try:
        cid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case id")

    case = await db.get(Case, cid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    summary = _summary(case)
    return CaseDetail(
        **summary.model_dump(),
        source_request_id=case.source_request_id,
        decision_id=str(case.decision_id) if case.decision_id else None,
        trace=case.trace.get("agents", []) if isinstance(case.trace, dict) else [],
    )


@router.post("/{case_id}/override", response_model=OverrideResponse)
async def override_case(
    case_id: str,
    payload: OverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_role("STAFF", "MANAGER", "ADMIN")),
):
    if payload.action not in ("ACCEPT", "REJECT"):
        raise HTTPException(status_code=400, detail="action must be ACCEPT or REJECT")
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="reason is required for an override")

    try:
        cid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case id")

    async with db.begin():
        case = await db.get(Case, cid)
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        case.status = CaseStatus.OVERRIDDEN

        override = CaseOverride(
            case_id=case.id,
            officer_user_id=uuid.UUID(current_user.user_id),
            officer_email=current_user.email,
            action=OverrideAction(payload.action),
            reason=payload.reason.strip(),
        )
        db.add(override)

        decision = await write_decision_with_intent(
            db,
            request_id=case.source_request_id,
            decision_type="CASE_OVERRIDE",
            outcome=payload.action,
            confidence=1.0,
            trace=[
                f"case_override: officer={current_user.email} case={case.id} "
                f"action={payload.action} reason=\"{payload.reason.strip()}\""
            ],
            redacted_context=None,
        )
        override.decision_id = decision.id

    decision_id = str(decision.id)

    return OverrideResponse(case_id=str(case.id), status=case.status.value, decision_id=decision_id)
