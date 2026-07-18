"""
Auditor agent tests. Pure outcome resolution + terminal behaviour, no DB.
"""

from __future__ import annotations

from app.swarm.agents.auditor import AuditorAgent, resolve_outcome
from app.swarm.context import SwarmContext
from app.swarm.core import Directive, Swarm


# ── resolve_outcome (pure) ────────────────────────────────────────────────────

def test_fraud_rejected_wins():
    assert resolve_outcome({"fraud_result": {"outcome": "REJECTED", "confidence": 0.95}})[0] == "REJECTED"


def test_fraud_flagged():
    out, conf, src = resolve_outcome({"fraud_result": {"outcome": "FLAGGED", "confidence": 0.7}})
    assert out == "FLAGGED" and src == "fraud_agent"


def test_fraud_overrides_identity_and_compliance():
    out, _c, src = resolve_outcome({
        "fraud_result": {"outcome": "REJECTED", "confidence": 0.9},
        "identity_result": {"outcome": "APPROVED"},
        "compliance_result": {"outcome": "APPROVED_STANDARD"},
    })
    assert out == "REJECTED" and src == "fraud_agent"


def test_identity_rejected():
    out, _c, src = resolve_outcome({"identity_result": {"outcome": "REJECTED", "confidence": 0.99}})
    assert out == "REJECTED" and src == "identity_agent"


def test_compliance_approved_fast_track():
    out, _c, src = resolve_outcome({"compliance_result": {"outcome": "APPROVED_FAST_TRACK", "confidence": 0.99}})
    assert out == "APPROVED" and src == "compliance_agent"


def test_cache_hit_wins():
    out, conf, src = resolve_outcome({
        "memory_hit": True,
        "cached_response": {"outcome": "APPROVED", "confidence": 0.88},
        "fraud_result": {"outcome": "REJECTED"},
    })
    assert out == "APPROVED" and conf == 0.88 and src == "cache"


def test_llm_answer_path():
    out, _c, src = resolve_outcome({"llm_response": "Per policy, approved."})
    assert out == "APPROVED" and src == "llm"


def test_fallback_needs_review():
    assert resolve_outcome({}) == ("NEEDS_REVIEW", 0.5, "fallback")


# ── agent (no DB) ─────────────────────────────────────────────────────────────

async def test_auditor_sets_final_outcome_and_score_without_db():
    ctx = SwarmContext(request_id="r1", request_type="CO_LENDING", raw_input="x")
    ctx.set("compliance_result", {"outcome": "APPROVED_STANDARD", "confidence": 0.99})
    ctx.handoff_path.extend(["guardrail", "knowledge", "identity_fraud"])

    directive = await AuditorAgent(db=None).run(ctx)

    assert isinstance(directive, Directive)
    assert ctx.get("final_outcome") == "APPROVED"
    assert ctx.get("confidence_score") == 99.0
    assert ctx.get("decision_id") is None
    assert any("confidence_score=99.0/100" in line for line in ctx.trace)


# ── integration: auditor as the Swarm terminal ────────────────────────────────

class _RejectingFraud:
    name = "identity_fraud"

    async def run(self, ctx: SwarmContext) -> Directive:
        ctx.set("fraud_result", {"outcome": "REJECTED", "confidence": 0.96})
        return Directive()


async def test_auditor_finalizes_as_swarm_terminal():
    swarm = Swarm([_RejectingFraud()], AuditorAgent(db=None))
    ctx = SwarmContext(request_id="r1", request_type="FRAUD_CHECK", raw_input="x")

    result = await swarm.run(ctx)

    assert result.handoff_path == ["identity_fraud", "auditor"]
    assert result.get("final_outcome") == "REJECTED"
    assert result.get("confidence_score") == 96.0
