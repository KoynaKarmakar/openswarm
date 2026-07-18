"""
Tests for the circular compliance gate.
Tests do NOT require Qdrant — they exercise the hard-rule evaluator and
chunker independently from the vector store.
"""

import pytest

from app.circulars.chunker import load_all_circular_chunks, _extract_rule_blocks
from app.circulars.gate import (
    CircularValidationResult,
    CircularComplianceGate,
    _evaluate_hard_rules,
)


# ── Chunker tests ─────────────────────────────────────────────────────────────

def test_chunker_loads_policies():
    chunks = load_all_circular_chunks()
    assert len(chunks) > 0, "Should load at least one chunk from sample_policies/"


def test_chunker_extracts_rule_ids():
    chunks = load_all_circular_chunks()
    all_rule_ids = set()
    for c in chunks:
        all_rule_ids.update(c.rule_ids)

    expected = {"CLM-001", "CLM-002", "CLM-003", "CLM-004",
                "UEBT-001", "UEBT-002", "UEBT-003", "UEBT-004",
                "KYC-001", "KYC-002", "KYC-003",
                "COMP-001", "COMP-002"}
    assert expected.issubset(all_rule_ids), f"Missing rule IDs: {expected - all_rule_ids}"


def test_chunker_rule_blocks_have_condition():
    chunks = load_all_circular_chunks()
    rule_chunks = [c for c in chunks if c.has_hard_rules]
    assert len(rule_chunks) > 0, "At least some chunks should have parsed rule blocks"
    for chunk in rule_chunks:
        for rb in chunk.rule_blocks:
            assert "rule_id" in rb, f"Rule block missing rule_id: {rb}"
            assert "outcome" in rb, f"Rule block missing outcome: {rb}"


def test_extract_rule_blocks_from_json():
    text = '''
## Rules
```json
[
  {
    "rule_id": "CLM-001",
    "description": "Approve fast track",
    "condition": {"risk_tier": "A", "kyc_status": "VERIFIED"},
    "outcome": "APPROVED_FAST_TRACK"
  }
]
```
'''
    rule_ids, blocks = _extract_rule_blocks(text)
    assert "CLM-001" in rule_ids
    assert len(blocks) == 1
    assert blocks[0]["outcome"] == "APPROVED_FAST_TRACK"


# ── Hard rule evaluator tests ─────────────────────────────────────────────────

FRAUD_RULES = [
    {
        "rule_id": "UEBT-003",
        "condition": {"fraud_score": {">": 0.85}},
        "outcome": "REJECTED",
    },
    {
        "rule_id": "UEBT-004",
        "condition": {"fraud_score": {"between": [0.6, 0.85]}},
        "outcome": "NEEDS_REVIEW",
    },
]

KYC_RULES = [
    {
        "rule_id": "KYC-001",
        "condition": {"kyc_status": "VERIFIED"},
        "outcome": "APPROVED",
    },
    {
        "rule_id": "KYC-003",
        "condition": {"kyc_status": {"in": ["REJECTED", "EXPIRED"]}},
        "outcome": "REJECTED",
        "reason": "Valid KYC required",
    },
]

CLM_RULES = [
    {
        "rule_id": "CLM-001",
        "condition": {"risk_tier": "A", "kyc_status": "VERIFIED"},
        "outcome": "APPROVED_FAST_TRACK",
    },
    {
        "rule_id": "CLM-004",
        "condition": {"kyc_status": {"not": "VERIFIED"}},
        "outcome": "REJECTED",
        "reason": "Co-lending requires verified KYC",
    },
]


def test_hard_rule_fraud_high_score():
    verdict, rule_id, reason = _evaluate_hard_rules(FRAUD_RULES, {"fraud_score": 0.92})
    assert verdict == "NON_COMPLIANT"
    assert rule_id == "UEBT-003"


def test_hard_rule_fraud_medium_score():
    verdict, rule_id, reason = _evaluate_hard_rules(FRAUD_RULES, {"fraud_score": 0.72})
    assert verdict == "NON_COMPLIANT"
    assert rule_id == "UEBT-004"


def test_hard_rule_fraud_low_score_no_fire():
    verdict, rule_id, reason = _evaluate_hard_rules(FRAUD_RULES, {"fraud_score": 0.20})
    assert verdict is None  # no rule fires for low scores


def test_hard_rule_kyc_rejected():
    verdict, rule_id, reason = _evaluate_hard_rules(KYC_RULES, {"kyc_status": "REJECTED"})
    assert verdict == "NON_COMPLIANT"
    assert rule_id == "KYC-003"
    assert "Valid KYC" in reason


def test_hard_rule_kyc_expired():
    verdict, rule_id, reason = _evaluate_hard_rules(KYC_RULES, {"kyc_status": "EXPIRED"})
    assert verdict == "NON_COMPLIANT"
    assert rule_id == "KYC-003"


def test_hard_rule_clm_unverified_kyc():
    verdict, rule_id, reason = _evaluate_hard_rules(CLM_RULES, {"kyc_status": "PENDING", "risk_tier": "A"})
    assert verdict == "NON_COMPLIANT"
    assert rule_id == "CLM-004"


def test_hard_rule_clm_verified_tier_a():
    verdict, rule_id, reason = _evaluate_hard_rules(CLM_RULES, {"kyc_status": "VERIFIED", "risk_tier": "A"})
    assert verdict == "COMPLIANT"
    assert rule_id == "CLM-001"


def test_hard_rule_no_context_no_fire():
    verdict, rule_id, reason = _evaluate_hard_rules(FRAUD_RULES, {})
    assert verdict is None  # empty context → no hard rule fires


# ── Gate with no store (pass-through) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_no_store_passthrough():
    gate = CircularComplianceGate(vector_store=None)
    result = await gate.validate("What is the co-lending policy?")
    assert result.valid is True
    assert result.phase == "no_circulars"


# ── CircularValidationResult serialisation ────────────────────────────────────

def test_result_to_dict():
    result = CircularValidationResult(
        valid=False,
        phase="hard_rule",
        verdict="NON_COMPLIANT",
        violated_rules=["UEBT-003"],
        relevant_circulars=["UEBT Policy — Fraud Agent Rules"],
        reason="Fraud score exceeds threshold",
        confidence=0.98,
    )
    d = result.to_dict()
    assert d["valid"] is False
    assert d["verdict"] == "NON_COMPLIANT"
    assert "UEBT-003" in d["violated_rules"]
