"""
📜 Agent 4 — Auditor (verification + logging). The deterministic terminal agent.

Always runs last, on every path through the swarm, so no decision escapes the
audit trail — the guarantee the LangGraph `decision_coordinator` provided.

Steps:
  1. **Resolve** the final outcome from the agent results (pure `resolve_outcome`,
     same precedence as decision_coordinator: fraud > identity > compliance > LLM).
  2. **Score & print** a 0-100 Confidence Score to the terminal.
  3. **Log** the decision into the SHA-256 hash-chain ledger via the outbox intent
     (`write_decision_with_intent`), atomically, when a DB session is provided.

The ledger/outbox import is deferred so importing this agent never pulls
SQLAlchemy; `resolve_outcome` is a pure function and unit-tested without a DB.
"""

from __future__ import annotations

import logging
import uuid

from app.swarm.context import SwarmContext
from app.swarm.core import Directive

logger = logging.getLogger("veritas.swarm.auditor")

_APPROVED_COMPLIANCE = ("APPROVED_FAST_TRACK", "APPROVED_STANDARD", "APPROVED")


def resolve_outcome(vars: dict) -> tuple[str, float, str]:
    """
    Determine (outcome, confidence, source) from the agent results.

    Precedence mirrors the LangGraph decision_coordinator exactly:
      cache → fraud(REJECTED/FLAGGED) → identity(REJECTED)
            → compliance(APPROVED*/REJECTED) → LLM → fallback
    """
    fraud = vars.get("fraud_result") or {}
    identity = vars.get("identity_result") or {}
    compliance = vars.get("compliance_result") or {}
    cached = vars.get("cached_response") or {}

    if vars.get("memory_hit") and cached:
        return cached.get("outcome", "NEEDS_REVIEW"), cached.get("confidence", 0.5), "cache"
    if fraud.get("outcome") == "REJECTED":
        return "REJECTED", fraud.get("confidence", 0.9), "fraud_agent"
    if fraud.get("outcome") == "FLAGGED":
        return "FLAGGED", fraud.get("confidence", 0.7), "fraud_agent"
    if identity.get("outcome") == "REJECTED":
        return "REJECTED", identity.get("confidence", 0.9), "identity_agent"
    if compliance.get("outcome") in _APPROVED_COMPLIANCE:
        return "APPROVED", compliance.get("confidence", 0.9), "compliance_agent"
    if compliance.get("outcome") == "REJECTED":
        return "REJECTED", compliance.get("confidence", 0.95), "compliance_agent"
    if identity.get("outcome") == "NEEDS_REVIEW":
        return "NEEDS_REVIEW", identity.get("confidence", 0.6), "identity_agent"
    if vars.get("llm_response"):
        return "APPROVED", 0.7, "llm"
    return "NEEDS_REVIEW", 0.5, "fallback"


class AuditorAgent:
    name = "auditor"

    def __init__(self, *, db=None):
        """db : AsyncSession. If None, the outcome is resolved and scored but no
        ledger row is written (used in tests / dry runs)."""
        self._db = db

    async def run(self, ctx: SwarmContext) -> Directive:
        outcome, confidence, source = resolve_outcome(ctx.vars)
        confidence_score = round(float(confidence) * 100, 1)

        # ── Confidence Score → terminal ─────────────────────────────────────
        path = " → ".join(ctx.handoff_path)
        logger.info(
            "AUDITOR │ outcome=%s │ confidence=%.1f/100 │ via=%s │ path=%s",
            outcome, confidence_score, source, path,
        )
        ctx.set("final_outcome", outcome)
        ctx.set("final_confidence", confidence)
        ctx.set("confidence_score", confidence_score)
        ctx.log(
            f"auditor: outcome={outcome} confidence_score={confidence_score}/100 "
            f"via={source} path=[{path}]"
        )

        # ── Hash-chain ledger write (atomic Decision + OutboxIntent) ─────────
        decision_id = None
        if self._db is not None:
            from app.ledger.outbox import write_decision_with_intent  # deferred

            request_id = ctx.request_id or str(uuid.uuid4())
            trace = ctx.trace + [f"auditor: outcome={outcome} via={source}"]
            try:
                async with self._db.begin():
                    decision = await write_decision_with_intent(
                        self._db,
                        request_id=request_id,
                        decision_type=ctx.request_type or "UNKNOWN",
                        outcome=outcome,
                        confidence=confidence,
                        trace=trace,
                        redacted_context=ctx.get("redacted_input"),
                    )
                decision_id = str(decision.id)
                ctx.log(f"auditor: ledger intent written decision_id={decision_id}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Auditor failed to write decision to ledger")
                ctx.log(f"auditor: ledger write FAILED — {exc}")
        else:
            ctx.log("auditor: no DB session — ledger write skipped (dry run)")

        ctx.set("decision_id", decision_id)
        return Directive(reason=f"final:{outcome}")
