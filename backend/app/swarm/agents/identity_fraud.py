"""
👤 Agent 3 — Identity & Fraud Validator.

Filled in on branch `agent-identity-fraud`. It will:
  * run the identity check (identity_agent.py) via the BankAdapter;
  * run the XGBoost fraud model (fraud_agent.py / ml/fraud_model.py);
  * verify a Google Verifiable Credential (cryptographic signature check) as the
    "verifiable authentic docs" connector, replacing today's mocked OCR/liveness.
  * on a REJECTED identity/fraud outcome it may Directive(halt=True) to the Auditor.

Placeholder below is a no-op pass-through.
"""

from __future__ import annotations

from app.swarm.context import SwarmContext
from app.swarm.core import Directive


class IdentityFraudAgent:
    name = "identity_fraud"

    def __init__(self, **_deps):
        # Base placeholder swallows injected deps (adapter);
        # the agent-identity-fraud branch tightens this signature.
        pass

    async def run(self, ctx: SwarmContext) -> Directive:
        ctx.log("identity_fraud: placeholder pass-through (base branch)")
        return Directive()
