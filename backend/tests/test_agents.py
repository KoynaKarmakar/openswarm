"""
Agent graph tests — verify routing logic and trace correctness.
No DB or LLM required: DB writes are mocked, LLM is never called in
hard-rule paths.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.base import AccountSummary, BankAdapter, IdentityRecord, TransactionSummary
from app.agents.compliance_agent import compliance_node
from app.agents.fraud_agent import fraud_node
from app.agents.identity_agent import identity_node
from app.agents.policy_agent import policy_node
from app.agents.state import VeritasState
from app.ledger.chain import GENESIS_HASH, ChainRecord, verify_chain


# ── Mock BankAdapter ─────────────────────────────────────────────────────────

class MockAdapter(BankAdapter):
    def __init__(self, kyc_status="VERIFIED", risk_tier="A", fraud_score=0.05):
        self._kyc_status = kyc_status
        self._risk_tier = risk_tier
        self._fraud_score = fraud_score

    async def verify_identity(self, customer_id: str) -> IdentityRecord:
        return IdentityRecord(
            customer_id=customer_id,
            full_name_redacted="R.K.",
            kyc_status=self._kyc_status,
            kyc_verified_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            risk_tier=self._risk_tier,
            co_lending_eligible=(self._kyc_status == "VERIFIED" and self._risk_tier in ("A", "B", "C")),
            did_credential={
                "type": "BankingIdentityCredential",
                "kyc_status": self._kyc_status,
                "risk_tier": self._risk_tier,
                "issuer": "did:idbi:veritas-fabric-v1",
            },
        )

    async def get_account(self, account_id: str) -> AccountSummary:
        return AccountSummary(
            account_id=account_id,
            account_type="SAVINGS",
            balance=50000.0,
            is_frozen=False,
            kyc_status=self._kyc_status,
        )

    async def get_transactions(self, account_id: str, limit: int = 20) -> list[TransactionSummary]:
        return [
            TransactionSummary(
                transaction_id=str(uuid.uuid4()),
                amount=1000.0,
                transaction_type="UPI",
                status="COMPLETED",
                merchant_name="Merchant A",
                location="Mumbai",
                created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
                fraud_score=self._fraud_score,
            )
        ]

    async def check_kyc_status(self, customer_id: str) -> str:
        return self._kyc_status


# ── Identity agent ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_identity_approved_when_kyc_verified():
    state = VeritasState(user_id="cust-001", trace=[], extra_context={})
    adapter = MockAdapter(kyc_status="VERIFIED", risk_tier="A")

    update = await identity_node(state, adapter)

    assert update["identity_result"]["outcome"] == "APPROVED"
    assert update["identity_result"]["rule_id"] == "KYC-001"
    assert update["identity_result"]["details"]["risk_tier"] == "A"
    assert any("identity_agent" in t for t in update["trace"])


@pytest.mark.asyncio
async def test_identity_rejected_when_kyc_expired():
    state = VeritasState(user_id="cust-002", trace=[], extra_context={})
    adapter = MockAdapter(kyc_status="EXPIRED")

    update = await identity_node(state, adapter)

    assert update["identity_result"]["outcome"] == "REJECTED"
    assert update["identity_result"]["rule_id"] == "KYC-003"


@pytest.mark.asyncio
async def test_identity_skipped_when_no_customer_id():
    state = VeritasState(trace=[], extra_context={})
    adapter = MockAdapter()

    update = await identity_node(state, adapter)

    assert update["identity_result"]["outcome"] == "NEEDS_REVIEW"
    assert any("no customer_id" in t for t in update["trace"])


# ── Fraud agent ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fraud_approved_on_low_score():
    state = VeritasState(account_id="acc-001", trace=[], extra_context={})
    adapter = MockAdapter(fraud_score=0.05)

    update = await fraud_node(state, adapter)

    assert update["fraud_result"]["outcome"] == "APPROVED"
    assert update["fraud_result"]["rule_id"] is None


@pytest.mark.asyncio
async def test_fraud_flagged_on_medium_score():
    state = VeritasState(account_id="acc-001", trace=[], extra_context={})
    adapter = MockAdapter(fraud_score=0.70)

    update = await fraud_node(state, adapter)

    assert update["fraud_result"]["outcome"] == "FLAGGED"
    assert update["fraud_result"]["rule_id"] == "UEBT-004"


@pytest.mark.asyncio
async def test_fraud_rejected_on_high_score():
    state = VeritasState(account_id="acc-001", trace=[], extra_context={})
    adapter = MockAdapter(fraud_score=0.92)

    update = await fraud_node(state, adapter)

    assert update["fraud_result"]["outcome"] == "REJECTED"
    assert update["fraud_result"]["rule_id"] == "UEBT-003"


# ── Compliance agent ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compliance_co_lending_tier_a_approved_fast_track():
    state = VeritasState(
        request_type="CO_LENDING",
        identity_result={
            "outcome": "APPROVED",
            "details": {"kyc_status": "VERIFIED", "risk_tier": "A"},
        },
        trace=[],
    )

    update = await compliance_node(state)

    assert update["compliance_result"]["outcome"] == "APPROVED_FAST_TRACK"
    assert update["compliance_result"]["rule_id"] == "CLM-001"
    assert update["rule_fired"] is True


@pytest.mark.asyncio
async def test_compliance_co_lending_rejected_unverified_kyc():
    state = VeritasState(
        request_type="CO_LENDING",
        identity_result={
            "outcome": "NEEDS_REVIEW",
            "details": {"kyc_status": "PENDING", "risk_tier": "A"},
        },
        trace=[],
    )

    update = await compliance_node(state)

    assert update["compliance_result"]["outcome"] == "REJECTED"
    assert update["compliance_result"]["rule_id"] == "CLM-004"
    assert update["rule_fired"] is True


@pytest.mark.asyncio
async def test_compliance_no_rule_for_unknown_type():
    state = VeritasState(
        request_type="GENERAL_QUERY",
        identity_result={"outcome": "APPROVED", "details": {"kyc_status": "VERIFIED", "risk_tier": "A"}},
        trace=[],
    )

    update = await compliance_node(state)

    assert update["rule_fired"] is False
    assert update["compliance_result"]["outcome"] == "NEEDS_REVIEW"


# ── Policy agent ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_policy_skipped_when_rule_fired():
    state = VeritasState(request_type="CO_LENDING", rule_fired=True, trace=[])
    update = await policy_node(state)
    assert any("skipped" in t for t in update["trace"])


@pytest.mark.asyncio
async def test_policy_routes_to_llm_when_no_rule():
    state = VeritasState(request_type="GENERAL_QUERY", rule_fired=False, trace=[])
    update = await policy_node(state)
    assert any("LLM" in t for t in update["trace"])


# ── Routing logic ─────────────────────────────────────────────────────────────

def test_route_after_memory_check_cache_hit():
    from app.agents.state import route_after_memory_check
    state = VeritasState(memory_hit=True, rule_fired=False, trace=[])
    assert route_after_memory_check(state) == "decision_coordinator"


def test_route_after_memory_check_rule_fired():
    from app.agents.state import route_after_memory_check
    state = VeritasState(memory_hit=False, rule_fired=True, trace=[])
    assert route_after_memory_check(state) == "decision_coordinator"


def test_route_after_memory_check_needs_llm():
    from app.agents.state import route_after_memory_check
    state = VeritasState(memory_hit=False, rule_fired=False, trace=[])
    assert route_after_memory_check(state) == "llm_call"


# ── Trace accumulation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trace_accumulates_across_agents():
    """Each agent appends to trace — verify multiple agents leave their marks."""
    adapter = MockAdapter(kyc_status="VERIFIED", risk_tier="A", fraud_score=0.05)
    base_state = VeritasState(
        user_id="cust-001",
        account_id="acc-001",
        request_type="CO_LENDING",
        trace=[],
        extra_context={},
    )

    id_update = await identity_node(base_state, adapter)
    assert len(id_update["trace"]) > 0

    state_after_id = {**base_state, **id_update}
    fraud_update = await fraud_node(state_after_id, adapter)
    assert len(fraud_update["trace"]) > 0

    state_after_fraud = {**state_after_id, **fraud_update}
    comp_update = await compliance_node(state_after_fraud)
    assert len(comp_update["trace"]) > 0

    # All traces have meaningful content
    all_traces = id_update["trace"] + fraud_update["trace"] + comp_update["trace"]
    assert any("identity_agent" in t for t in all_traces)
    assert any("fraud_agent" in t for t in all_traces)
    assert any("compliance_agent" in t for t in all_traces)


# ── DID credential schema ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_did_credential_schema_is_multi_issuer_ready():
    """DID credential must look multi-issuer-ready even though we're single-issuer."""
    adapter = MockAdapter(kyc_status="VERIFIED", risk_tier="A")
    state = VeritasState(user_id="cust-001", trace=[], extra_context={})
    update = await identity_node(state, adapter)

    cred = update["identity_result"]["details"]["did_credential"]
    assert "type" in cred
    assert "kyc_status" in cred
    assert "risk_tier" in cred
    assert "issuer" in cred
    assert cred["issuer"].startswith("did:")  # DID format
    # No raw PII in the credential
    assert "pan" not in str(cred).lower()
    assert "aadhaar" not in str(cred).lower()
    assert "phone" not in str(cred).lower()
