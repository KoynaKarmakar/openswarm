from __future__ import annotations

import logging

from app.agents.state import AgentResult, VeritasState

logger = logging.getLogger("veritas.compliance")

# Hard rules loaded from policy docs — CLM, UEBT, KYC
# Step 3 will add Qdrant RAG retrieval for rules not covered here
_CO_LENDING_RULES = {
    "A": ("APPROVED_FAST_TRACK", "CLM-001"),
    "B": ("APPROVED_STANDARD", "CLM-002"),
    "C": ("APPROVED_STANDARD", "CLM-002"),
    "D": ("NEEDS_REVIEW", "CLM-003"),
}


async def compliance_node(state: VeritasState) -> dict:
    """
    Run hard policy rules from the IDBI policy set.
    Does NOT call an LLM — pure rule evaluation.

    Returns rule_fired=True if a hard rule resolved the request so
    memory_check can skip the LLM path.

    Step 2: core CLM + KYC hard rules.
    Step 3: adds RAG retrieval for soft policy questions.
    """
    identity = state.get("identity_result") or {}
    details = identity.get("details", {})
    request_type = state.get("request_type", "")

    # Co-lending eligibility path
    if request_type == "CO_LENDING":
        risk_tier = details.get("risk_tier", "D")
        kyc_status = details.get("kyc_status", "PENDING")

        if kyc_status != "VERIFIED":
            return {
                "compliance_result": AgentResult(
                    outcome="REJECTED",
                    confidence=1.0,
                    rule_id="CLM-004",
                    details={"reason": "KYC not verified", "kyc_status": kyc_status},
                ),
                "rule_fired": True,
                "trace": [f"compliance_agent: CLM-004 fired (kyc_status={kyc_status})"],
            }

        outcome, rule_id = _CO_LENDING_RULES.get(risk_tier, ("NEEDS_REVIEW", "CLM-003"))
        return {
            "compliance_result": AgentResult(
                outcome=outcome,
                confidence=0.99,
                rule_id=rule_id,
                details={"risk_tier": risk_tier, "co_lending_rule": rule_id},
            ),
            "rule_fired": True,
            "trace": [f"compliance_agent: {rule_id} fired (risk_tier={risk_tier} → {outcome})"],
        }

    # Generic compliance check — no hard rule covers this, LLM path needed
    return {
        "compliance_result": AgentResult(
            outcome="NEEDS_REVIEW",
            confidence=0.5,
            rule_id=None,
            details={"note": "no hard rule matched — routing to LLM path"},
        ),
        "rule_fired": False,
        "trace": [f"compliance_agent: no hard rule for request_type={request_type}"],
    }
