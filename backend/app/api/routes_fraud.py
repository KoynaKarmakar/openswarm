import logging
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import TokenData
from app.db import get_db
from app.ledger.outbox import write_decision_with_intent

logger = logging.getLogger("veritas.fraud_route")
router = APIRouter(prefix="/fraud", tags=["fraud"])


class FraudCheckRequest(BaseModel):
    account_id: str
    transaction_id: str | None = None
    request_id: str | None = None


class FraudCheckResponse(BaseModel):
    request_id: str
    decision_id: str | None
    outcome: str
    fraud_score: float | None
    confidence: float | None
    rule_id: str | None
    transactions_checked: int
    trace: list[str]
    health_score: dict | None


@router.post("/check", response_model=FraudCheckResponse)
async def check_fraud(
    payload: FraudCheckRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    adapter = request.app.state.bank_adapter
    request_id = payload.request_id or str(uuid.uuid4())

    from app.agents.fraud_agent import fraud_node
    from app.agents.state import VeritasState

    state = VeritasState(
        request_id=request_id,
        request_type="FRAUD_CHECK",
        account_id=payload.account_id,
        transaction_id=payload.transaction_id,
        trace=[],
        extra_context={},
    )

    update = await fraud_node(state, adapter)
    result = update.get("fraud_result", {})
    details = result.get("details", {})

    outcome = result.get("outcome", "NEEDS_REVIEW")

    try:
        async with db.begin():
            decision = await write_decision_with_intent(
                db,
                request_id=request_id,
                decision_type="FRAUD_CHECK",
                outcome=outcome,
                confidence=result.get("confidence"),
                trace=update.get("trace", []),
                redacted_context=None,
            )
        decision_id = str(decision.id)
    except Exception:
        decision_id = None
        decision = None

    if outcome in ("FLAGGED", "NEEDS_REVIEW", "REJECTED"):
        try:
            from app.agents.case_rules import derive_liability
            from app.adapters.mock_adapter import MockBankAdapter
            from app.models.case import Case

            customer_id = None
            if isinstance(adapter, MockBankAdapter):
                cust = adapter.get_customer_for_account(payload.account_id)
                customer_id = cust.get("customer_id") if cust else None

            liability = derive_liability(details.get("fraud_score"), result.get("rule_id"))

            async with db.begin():
                db.add(Case(
                    source_request_id=request_id,
                    account_id=payload.account_id,
                    customer_id=customer_id,
                    fraud_score=details.get("fraud_score"),
                    rule_id=result.get("rule_id"),
                    liability_tier=liability.tier,
                    compensation_percent=liability.compensation_percent,
                    sla_deadline=liability.sla_deadline,
                    decision_id=decision.id if decision else None,
                    trace={"agents": update.get("trace", [])},
                ))
        except Exception:
            logger.exception("Failed to auto-create Case for request %s", request_id)

    return FraudCheckResponse(
        request_id=request_id,
        decision_id=decision_id,
        outcome=result.get("outcome", "NEEDS_REVIEW"),
        fraud_score=details.get("fraud_score"),
        confidence=result.get("confidence"),
        rule_id=result.get("rule_id"),
        transactions_checked=details.get("transactions_checked", 0),
        trace=update.get("trace", []),
        health_score=details.get("health_score"),
    )
