"""
Hash chain integrity tests — pure function tests, no DB required.

Verifies:
1. A correctly computed chain is valid.
2. Tampering any field (payload, hash, order) is detected.
3. Genesis record uses the correct zero-hash prefix.
4. Single-record chains work.
5. Empty chains are valid (nothing to verify).
"""

import json
import pytest

from app.ledger.chain import (
    GENESIS_HASH,
    ChainRecord,
    canonical_json,
    compute_hash,
    verify_chain,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def build_chain(n: int) -> list[ChainRecord]:
    """Build a valid chain of n records from genesis."""
    records = []
    prev_hash = GENESIS_HASH
    for i in range(n):
        payload = {
            "decision_id": f"decision-{i:04d}",
            "request_id": f"req-{i:04d}",
            "decision_type": "FRAUD_CHECK",
            "outcome": "APPROVED",
            "trace": [f"agent_{i}: ran"],
        }
        payload_str = canonical_json(payload)
        created_at = f"2026-01-{i+1:02d}T10:00:00+00:00"
        curr_hash = compute_hash(prev_hash, payload_str, created_at)
        records.append(
            ChainRecord(
                id=f"record-{i:04d}",
                prev_hash=prev_hash,
                curr_hash=curr_hash,
                payload_json=payload,
                created_at=created_at,
            )
        )
        prev_hash = curr_hash
    return records


# ── Validity tests ────────────────────────────────────────────────────────────

def test_valid_chain_of_one():
    chain = build_chain(1)
    result = verify_chain(chain)
    assert result.valid is True
    assert result.total_records == 1
    assert result.first_invalid_index is None


def test_valid_chain_of_ten():
    chain = build_chain(10)
    result = verify_chain(chain)
    assert result.valid is True
    assert result.total_records == 10


def test_empty_chain_is_valid():
    result = verify_chain([])
    assert result.valid is True
    assert result.total_records == 0


def test_genesis_record_uses_zero_hash():
    chain = build_chain(3)
    assert chain[0].prev_hash == GENESIS_HASH
    assert chain[0].prev_hash == "0" * 64


# ── Tampering detection ───────────────────────────────────────────────────────

def test_tampered_payload_breaks_chain():
    chain = build_chain(5)
    # Silently change a payload field mid-chain
    chain[2].payload_json = dict(chain[2].payload_json)
    chain[2].payload_json["outcome"] = "REJECTED"  # was APPROVED

    result = verify_chain(chain)
    assert result.valid is False
    assert result.first_invalid_index == 2
    assert result.first_invalid_id == "record-0002"


def test_tampered_curr_hash_breaks_chain():
    chain = build_chain(4)
    original_hash = chain[1].curr_hash
    chain[1].curr_hash = "a" * 64  # corrupt the stored hash

    result = verify_chain(chain)
    assert result.valid is False
    assert result.first_invalid_index == 1


def test_tampered_prev_hash_breaks_chain():
    """Changing prev_hash on record N should be caught at record N."""
    chain = build_chain(4)
    chain[2].prev_hash = "b" * 64  # doesn't match chain[1].curr_hash

    result = verify_chain(chain)
    assert result.valid is False
    assert result.first_invalid_index == 2


def test_reordered_records_break_chain():
    """Swapping two records breaks the prev_hash linkage."""
    chain = build_chain(5)
    chain[1], chain[2] = chain[2], chain[1]  # swap

    result = verify_chain(chain)
    assert result.valid is False
    assert result.first_invalid_index is not None  # breaks somewhere


def test_deleted_record_breaks_chain():
    """Removing record N causes record N+1's prev_hash to point to the wrong place."""
    chain = build_chain(5)
    del chain[2]  # remove middle record

    result = verify_chain(chain)
    assert result.valid is False


def test_appended_fake_record_breaks_chain():
    """A record appended with a forged prev_hash is caught."""
    chain = build_chain(3)
    last = chain[-1]
    fake_payload = {"decision_id": "fake", "outcome": "APPROVED", "trace": []}
    fake_created_at = "2026-12-31T23:59:59+00:00"
    # Use wrong prev_hash (genesis instead of last.curr_hash)
    fake_curr_hash = compute_hash(GENESIS_HASH, canonical_json(fake_payload), fake_created_at)
    chain.append(
        ChainRecord(
            id="fake-record",
            prev_hash=GENESIS_HASH,  # wrong — should be last.curr_hash
            curr_hash=fake_curr_hash,
            payload_json=fake_payload,
            created_at=fake_created_at,
        )
    )

    result = verify_chain(chain)
    assert result.valid is False
    assert result.first_invalid_id == "fake-record"


# ── Hash function properties ──────────────────────────────────────────────────

def test_same_inputs_produce_same_hash():
    h1 = compute_hash("aaaa", '{"x":1}', "2026-01-01T00:00:00+00:00")
    h2 = compute_hash("aaaa", '{"x":1}', "2026-01-01T00:00:00+00:00")
    assert h1 == h2


def test_different_timestamp_changes_hash():
    h1 = compute_hash("aaaa", '{"x":1}', "2026-01-01T00:00:00+00:00")
    h2 = compute_hash("aaaa", '{"x":1}', "2026-01-02T00:00:00+00:00")
    assert h1 != h2


def test_canonical_json_is_stable():
    payload = {"z": 3, "a": 1, "m": 2}
    s1 = canonical_json(payload)
    s2 = canonical_json({"m": 2, "z": 3, "a": 1})
    assert s1 == s2
    assert s1 == '{"a":1,"m":2,"z":3}'


def test_hash_length_is_64_hex_chars():
    h = compute_hash(GENESIS_HASH, '{"x":1}', "2026-01-01T00:00:00+00:00")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
