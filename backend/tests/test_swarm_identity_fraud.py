"""
Identity & Fraud agent + Google Verifiable Credentials connector tests.

Signature tests need `cryptography`; skipped cleanly if it is unavailable.
Engine nodes (identity/fraud) are injected as fakes so XGBoost/spaCy aren't imported.
"""

from __future__ import annotations

import pytest

from app.swarm.agents.identity_fraud import IdentityFraudAgent
from app.swarm.connectors import GoogleVerifiableCredentialsConnector
from app.swarm.connectors.google_vc import (
    generate_issuer_keypair,
    issue_credential,
)
from app.swarm.context import SwarmContext

crypto = pytest.importorskip("cryptography")

ISSUER = "did:web:issuer.google.com"


@pytest.fixture
def keypair():
    return generate_issuer_keypair()  # (priv_b64, pub_b64)


@pytest.fixture
def connector(keypair):
    _priv, pub = keypair
    return GoogleVerifiableCredentialsConnector(trust_registry={ISSUER: pub})


# ── connector ─────────────────────────────────────────────────────────────────

def test_vc_valid_signature_verifies(connector, keypair):
    priv, _pub = keypair
    vc = issue_credential({"id": "did:example:alice", "kyc": "VERIFIED"},
                          issuer=ISSUER, private_key_b64=priv)
    result = connector.verify(vc)
    assert result.verified is True
    assert result.signature_state == "valid"
    assert result.issuer_trusted is True


def test_vc_tampered_signature_invalid(connector, keypair):
    priv, _pub = keypair
    vc = issue_credential({"id": "did:example:alice", "kyc": "VERIFIED"},
                          issuer=ISSUER, private_key_b64=priv)
    vc["credentialSubject"]["kyc"] = "REJECTED"   # tamper after signing
    result = connector.verify(vc)
    assert result.verified is False
    assert result.signature_state == "invalid"


def test_vc_untrusted_issuer_unchecked(keypair):
    priv, _pub = keypair
    vc = issue_credential({"id": "did:example:alice", "kyc": "VERIFIED"},
                          issuer=ISSUER, private_key_b64=priv)
    empty = GoogleVerifiableCredentialsConnector(trust_registry={})   # issuer unknown
    result = empty.verify(vc)
    assert result.verified is False
    assert result.issuer_trusted is False
    assert result.signature_state == "unchecked"


def test_vc_expired(connector, keypair):
    priv, _pub = keypair
    vc = issue_credential({"id": "did:example:alice", "kyc": "VERIFIED"},
                          issuer=ISSUER, private_key_b64=priv,
                          valid_until="2000-01-01T00:00:00Z")
    result = connector.verify(vc)
    assert result.expired is True
    assert result.verified is False


def test_vc_missing_fields_not_structural():
    result = GoogleVerifiableCredentialsConnector().verify({"type": ["VerifiableCredential"]})
    assert result.structural_ok is False
    assert result.verified is False


def test_vc_empty_credential():
    result = GoogleVerifiableCredentialsConnector().verify({})
    assert result.verified is False
    assert result.reason == "no credential presented"


# ── agent (fake identity/fraud nodes) ─────────────────────────────────────────

async def _fake_identity(state, adapter):
    return {
        "identity_result": {
            "outcome": "APPROVED", "confidence": 0.97, "rule_id": "KYC-001",
            "details": {"kyc_status": "VERIFIED"},
        },
        "trace": ["identity: APPROVED"],
    }


async def _fake_fraud(state, adapter):
    return {
        "fraud_result": {"outcome": "APPROVED", "confidence": 0.9, "details": {"fraud_score": 0.1}},
        "trace": ["fraud: APPROVED"],
    }


def _agent(connector):
    return IdentityFraudAgent(
        adapter=object(), vc_connector=connector,
        identity_fn=_fake_identity, fraud_fn=_fake_fraud,
    )


def _ctx_with_vc(vc):
    c = SwarmContext(request_id="r1", request_type="IDENTITY", raw_input="onboard me")
    c.extra_context["verifiable_credential"] = vc
    return c


async def test_agent_valid_vc_keeps_approved(connector, keypair):
    priv, _pub = keypair
    vc = issue_credential({"id": "did:example:alice", "kyc": "VERIFIED"},
                          issuer=ISSUER, private_key_b64=priv)
    ctx = _ctx_with_vc(vc)

    directive = await _agent(connector).run(ctx)

    identity = ctx.get("identity_result")
    assert identity["outcome"] == "APPROVED"
    assert identity["details"]["vc_verification"]["verified"] is True
    assert directive.halt is False and directive.next_agent is None  # → terminal Auditor


async def test_agent_invalid_vc_rejects_identity(connector, keypair):
    priv, _pub = keypair
    vc = issue_credential({"id": "did:example:alice", "kyc": "VERIFIED"},
                          issuer=ISSUER, private_key_b64=priv)
    vc["credentialSubject"]["kyc"] = "REJECTED"  # tamper
    ctx = _ctx_with_vc(vc)

    await _agent(connector).run(ctx)

    identity = ctx.get("identity_result")
    assert identity["outcome"] == "REJECTED"
    assert identity["rule_id"] == "VC-002"


async def test_agent_unchecked_vc_downgrades_to_review(keypair):
    priv, _pub = keypair
    vc = issue_credential({"id": "did:example:alice", "kyc": "VERIFIED"},
                          issuer=ISSUER, private_key_b64=priv)
    # untrusted issuer → signature unchecked
    ctx = _ctx_with_vc(vc)

    await _agent(GoogleVerifiableCredentialsConnector(trust_registry={})).run(ctx)

    identity = ctx.get("identity_result")
    assert identity["outcome"] == "NEEDS_REVIEW"
    assert identity["rule_id"] == "VC-003"


async def test_agent_no_credential_no_crash():
    ctx = SwarmContext(request_id="r1", request_type="IDENTITY", raw_input="onboard me")
    agent = IdentityFraudAgent(adapter=object(), identity_fn=_fake_identity, fraud_fn=_fake_fraud)

    directive = await agent.run(ctx)

    assert ctx.get("identity_result")["outcome"] == "APPROVED"
    assert directive.halt is False
