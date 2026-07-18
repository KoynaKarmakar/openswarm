from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.adapters.base import BankAdapter
from app.agents.state import AgentResult, VeritasState

logger = logging.getLogger("veritas.identity")

# KYC age thresholds in days
KYC_EXPIRY_DAYS = 730   # 2 years — from KYC/Digital Banking Policy


async def identity_node(state: VeritasState, adapter: BankAdapter) -> dict:
    """
    Verify customer identity via the BankAdapter.
    Issues a DID-ready credential (W3C VC 2.0 schema) on success.
    Evaluates co-lending eligibility from risk_tier (used by compliance_agent).
    """
    customer_id = state.get("user_id") or state.get("extra_context", {}).get("customer_id")

    if not customer_id:
        return {
            "identity_result": AgentResult(
                outcome="NEEDS_REVIEW",
                confidence=0.0,
                rule_id=None,
                details={"reason": "no customer_id in request"},
            ),
            "trace": ["identity_agent: skipped — no customer_id"],
        }

    try:
        record = await adapter.verify_identity(customer_id)
    except Exception as exc:
        logger.exception("Identity agent error for customer %s", customer_id)
        return {
            "identity_result": AgentResult(
                outcome="NEEDS_REVIEW", confidence=0.0, details={"error": str(exc)},
            ),
            "trace": [f"identity_agent: error — {exc}"],
        }

    kyc = record.kyc_status
    now = datetime.now(timezone.utc)

    # Check KYC age against policy KYC-002
    kyc_age_days = None
    if record.kyc_verified_at:
        kyc_age_days = (now - record.kyc_verified_at).days

    if kyc == "VERIFIED" and kyc_age_days and kyc_age_days >= KYC_EXPIRY_DAYS:
        outcome, rule = "NEEDS_REVIEW", "KYC-002"
        confidence = 0.6
        note = f"KYC verified {kyc_age_days} days ago — re-KYC required (>={KYC_EXPIRY_DAYS} days)"
    elif kyc == "VERIFIED":
        outcome, rule = "APPROVED", "KYC-001"
        confidence = 0.97
        note = f"KYC verified {kyc_age_days} days ago"
    elif kyc in ("REJECTED", "EXPIRED"):
        outcome, rule = "REJECTED", "KYC-003"
        confidence = 0.99
        note = f"KYC status={kyc}"
    else:
        outcome, rule = "NEEDS_REVIEW", "KYC-002"
        confidence = 0.5
        note = f"KYC status={kyc} — verification pending"

    return {
        "identity_result": AgentResult(
            outcome=outcome,
            confidence=confidence,
            rule_id=rule,
            details={
                "kyc_status": kyc,
                "kyc_age_days": kyc_age_days,
                "risk_tier": record.risk_tier,
                "co_lending_eligible": record.co_lending_eligible,
                "did_credential": record.did_credential,
                "note": note,
            },
        ),
        "trace": [
            f"identity_agent: kyc={kyc} risk_tier={record.risk_tier} "
            f"co_lending={record.co_lending_eligible} rule={rule} → {outcome}"
        ],
    }
