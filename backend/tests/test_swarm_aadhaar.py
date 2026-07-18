"""
Aadhaar Auth connector (UIDAI Auth 2.5-shaped) + agent integration tests.
DEMO mode only — no network, no real Aadhaar numbers (UIDAI test series 9999...).
"""

from __future__ import annotations

import pytest

from app.swarm.agents.identity_fraud import IdentityFraudAgent
from app.swarm.connectors import AadhaarAuthConnector, AuaConfig
from app.swarm.connectors.aadhaar_auth import mask_aadhaar, verhoeff_valid
from app.swarm.context import SwarmContext

VALID = "999941057058"   # UIDAI published test-series number (Verhoeff-valid)


# ── Verhoeff + masking ────────────────────────────────────────────────────────

def test_verhoeff_accepts_test_series():
    for uid in ["999941057058", "999971658846", "999933119400", "999955183437"]:
        assert verhoeff_valid(uid) is True


def test_verhoeff_rejects_bad_check_digit():
    assert verhoeff_valid("999941057059") is False   # last digit flipped
    assert verhoeff_valid("123456789012") is False
    assert verhoeff_valid("99994105705") is False     # 11 digits
    assert verhoeff_valid("abcd41057058") is False


def test_mask_shows_only_last_four():
    assert mask_aadhaar("999941057058") == "XXXX XXXX 7058"
    assert mask_aadhaar("9999 4105 7058") == "XXXX XXXX 7058"
    assert mask_aadhaar("bad") == "XXXX XXXX XXXX"


# ── connector (demo) ──────────────────────────────────────────────────────────

def test_demo_valid_uid_returns_y():
    r = AadhaarAuthConnector().verify(VALID)
    assert r.ret == "y" and r.err is None and r.outcome == "APPROVED"
    assert r.masked_uid == "XXXX XXXX 7058"


def test_demo_bad_checksum_998():
    r = AadhaarAuthConnector().verify("999941057059")
    assert r.ret == "n" and r.err == "998" and r.outcome == "REJECTED"


def test_demo_verhoeff_ok_but_unknown_uid_998():
    # valid checksum but not seeded → "no data" in demo
    assert verhoeff_valid("123456789010") is True
    r = AadhaarAuthConnector().verify("123456789010")
    assert r.ret == "n" and r.err == "998"


def test_demo_demographic_mismatch_k100():
    r = AadhaarAuthConnector().verify(VALID, name="Wrong Name")
    assert r.ret == "n" and r.err == "k-100" and r.outcome == "NEEDS_REVIEW"


def test_demo_demographic_match_y():
    r = AadhaarAuthConnector().verify(VALID, name="Shivshankar Choudhury", yob="1968")
    assert r.ret == "y"


def test_demo_otp_flow():
    assert AadhaarAuthConnector().verify(VALID, otp="123456").ret == "y"
    bad = AadhaarAuthConnector().verify(VALID, otp="000000")
    assert bad.ret == "n" and bad.err == "400"


def test_live_mode_refuses_to_transmit():
    conn = AadhaarAuthConnector(AuaConfig(mode="live"))
    with pytest.raises(NotImplementedError):
        conn.verify(VALID)


def test_envelope_masks_uid_and_has_shape():
    env = AadhaarAuthConnector().build_auth_envelope("999941057058", name="X", yob=None, otp=None, txn="t1")
    assert env["Auth"]["uid"] == "XXXX XXXX 7058"      # never the raw uid
    assert env["Auth"]["ver"] == "2.5"
    assert env["Auth"]["Uses"]["pi"] == "y"


# ── agent integration (raw Aadhaar must never leak) ───────────────────────────

async def _fake_identity(state, adapter):
    return {"identity_result": {"outcome": "APPROVED", "confidence": 0.97, "rule_id": None,
                                "details": {"kyc_status": "VERIFIED"}}, "trace": ["identity: APPROVED"]}


async def _fake_fraud(state, adapter):
    return {"fraud_result": {"outcome": "APPROVED", "confidence": 0.9, "details": {"fraud_score": 0.1}},
            "trace": ["fraud: APPROVED"]}


def _agent():
    return IdentityFraudAgent(adapter=object(), identity_fn=_fake_identity, fraud_fn=_fake_fraud)


def _ctx(extra):
    return SwarmContext(request_id="r1", request_type="IDENTITY", raw_input="verify me", extra_context=extra)


async def test_agent_aadhaar_verified_annotates_identity():
    ctx = _ctx({"aadhaar": VALID, "aadhaar_name": "Shivshankar Choudhury"})
    await _agent().run(ctx)

    identity = ctx.get("identity_result")
    assert identity["outcome"] == "APPROVED"
    aa = identity["details"]["aadhaar_auth"]
    assert aa["ret"] == "y" and aa["masked_uid"] == "XXXX XXXX 7058"
    # raw Aadhaar must never land in state or trace
    assert VALID not in str(ctx.vars)
    assert VALID not in " ".join(ctx.trace)


async def test_agent_bad_aadhaar_rejects():
    ctx = _ctx({"aadhaar": "999941057059"})   # bad checksum
    await _agent().run(ctx)

    identity = ctx.get("identity_result")
    assert identity["outcome"] == "REJECTED"
    assert identity["rule_id"] == "AADHAAR-002"
    assert "999941057059" not in " ".join(ctx.trace)


async def test_agent_no_aadhaar_is_noop():
    ctx = _ctx({})
    await _agent().run(ctx)
    assert "aadhaar_auth" not in (ctx.get("identity_result") or {}).get("details", {})


async def test_agent_live_mode_routes_to_review():
    agent = IdentityFraudAgent(
        adapter=object(), identity_fn=_fake_identity, fraud_fn=_fake_fraud,
        aadhaar_connector=AadhaarAuthConnector(AuaConfig(mode="live")),
    )
    ctx = _ctx({"aadhaar": VALID})
    await agent.run(ctx)
    assert ctx.get("identity_result")["outcome"] == "NEEDS_REVIEW"
