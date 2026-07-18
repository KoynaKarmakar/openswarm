"""
👤 Agent 3 — Identity & Fraud Validator.

Three checks, then hands off to the Auditor (the last dynamic-zone agent):

  1. **Identity** — reuse the tested `identity_node` (KYC via the BankAdapter,
     issues a DID-ready credential).
  2. **Fraud** — reuse the tested `fraud_node` (XGBoost score + UEBT thresholds).
  3. **Verifiable Credential** — verify a presented W3C VC (Google Wallet /
     Digital Credentials style) via GoogleVerifiableCredentialsConnector. This is
     the "verifiable authentic docs" connector — a cryptographic signature check,
     replacing spoofable OCR/liveness mocks.

VC outcome adjusts the identity result:
  * signature "invalid" OR untrusted issuer OR expired ⇒ identity REJECTED (VC-002)
  * signature "unchecked" (no key / cryptography absent) ⇒ downgrade an APPROVED
    identity to NEEDS_REVIEW (VC-003)
  * "valid" ⇒ annotate identity as VC-verified (VC-001)

The heavy engine nodes are imported lazily (and are injectable) so importing this
agent never pulls XGBoost/spaCy; tests inject fakes.
"""

from __future__ import annotations

import logging

from app.swarm.connectors import GoogleVerifiableCredentialsConnector
from app.swarm.context import SwarmContext
from app.swarm.core import Directive

logger = logging.getLogger("veritas.swarm.identity_fraud")


class IdentityFraudAgent:
    name = "identity_fraud"

    def __init__(self, *, adapter=None, vc_connector=None, identity_fn=None, fraud_fn=None):
        """
        adapter      : BankAdapter. If None, identity/fraud checks are skipped.
        vc_connector : GoogleVerifiableCredentialsConnector. Defaults to one with
                       an empty trust registry (every VC → "unchecked").
        identity_fn / fraud_fn : injectable node coroutines for tests; default to
                       the real identity_node / fraud_node (imported lazily).
        """
        self._adapter = adapter
        self._vc = vc_connector or GoogleVerifiableCredentialsConnector()
        self._identity_fn = identity_fn
        self._fraud_fn = fraud_fn

    def _identity(self):
        if self._identity_fn is not None:
            return self._identity_fn
        from app.agents.identity_agent import identity_node
        return identity_node

    def _fraud(self):
        if self._fraud_fn is not None:
            return self._fraud_fn
        from app.agents.fraud_agent import fraud_node
        return fraud_node

    async def run(self, ctx: SwarmContext) -> Directive:
        # ── 1 & 2. identity + fraud via the existing engine nodes ────────────
        if self._adapter is not None:
            ctx.absorb(await self._identity()(ctx.snapshot_state(), self._adapter))
            ctx.absorb(await self._fraud()(ctx.snapshot_state(), self._adapter))
        else:
            ctx.log("identity_fraud: no adapter — identity/fraud checks skipped")

        # ── 3. Verifiable Credential (Google) ────────────────────────────────
        self._apply_vc(ctx)

        return Directive(reason="identity/fraud complete → Auditor")

    # ── VC handling ──────────────────────────────────────────────────────────
    def _presented_credential(self, ctx: SwarmContext) -> dict | None:
        # Customer-presented VC takes priority; fall back to the bank-issued
        # DID credential attached by the identity node.
        vc = ctx.extra_context.get("verifiable_credential")
        if isinstance(vc, dict) and vc:
            return vc
        identity = ctx.get("identity_result") or {}
        did = (identity.get("details") or {}).get("did_credential")
        return did if isinstance(did, dict) and did else None

    def _apply_vc(self, ctx: SwarmContext) -> None:
        vc = self._presented_credential(ctx)
        if not vc:
            ctx.log("identity_fraud/vc: no credential presented — skipped")
            return

        result = self._vc.verify(vc)
        identity = dict(ctx.get("identity_result") or {})
        details = dict(identity.get("details") or {})
        details["vc_verification"] = result.to_dict()

        if not result.verified and (result.signature_state == "invalid"
                                    or (not result.issuer_trusted and result.signature_state != "unchecked")
                                    or result.expired):
            identity["outcome"] = "REJECTED"
            identity["confidence"] = 0.99
            identity["rule_id"] = "VC-002"
            details["vc_note"] = f"credential rejected ({result.reason})"
            ctx.log(f"identity_fraud/vc: REJECTED — {result.reason}")
        elif result.signature_state == "unchecked":
            if identity.get("outcome") == "APPROVED":
                identity["outcome"] = "NEEDS_REVIEW"
                identity["confidence"] = min(float(identity.get("confidence", 0.6)), 0.6)
                identity["rule_id"] = "VC-003"
            details["vc_note"] = f"signature unchecked ({result.reason})"
            ctx.log(f"identity_fraud/vc: signature UNCHECKED — {result.reason}")
        else:
            details["vc_note"] = "credential verified"
            if not identity.get("rule_id"):
                identity["rule_id"] = "VC-001"
            ctx.log(
                f"identity_fraud/vc: VERIFIED issuer={result.issuer} "
                f"signature={result.signature_state}"
            )

        identity["details"] = details
        ctx.set("identity_result", identity)
