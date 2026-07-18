"""
SHA-256 hash chain for the VERITAS audit ledger.

This is NOT Hyperledger — it is an application-layer hash chain stored in
Postgres. It provides tamper-evidence: any row modification breaks all
subsequent hashes, making silent edits detectable via /audit/verify.

Chain formula:
    curr_hash = SHA256( prev_hash + payload_json + created_at_iso )

The genesis (first) record uses GENESIS_HASH as prev_hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

GENESIS_HASH = "0" * 64


def compute_hash(prev_hash: str, payload_json: str, created_at: str) -> str:
    """
    Deterministic: same inputs always produce the same hash.
    created_at must be an ISO-8601 string with timezone (e.g. from .isoformat()).
    payload_json must be the canonical JSON string (sort_keys=True, no extra whitespace).
    """
    raw = prev_hash + payload_json + created_at
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_json(payload: dict) -> str:
    """Stable JSON serialisation — sort keys, no extra whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class ChainRecord:
    id: str
    prev_hash: str
    curr_hash: str
    payload_json: dict
    created_at: str  # ISO-8601 with tz


@dataclass
class VerifyResult:
    valid: bool
    total_records: int
    first_invalid_index: int | None = None  # 0-based
    first_invalid_id: str | None = None
    reason: str | None = None


def verify_chain(records: list[ChainRecord]) -> VerifyResult:
    """
    Walk the chain in order and re-compute each hash.
    Returns VerifyResult with the first detected break, if any.

    Records must be pre-ordered by created_at ascending (as stored).
    An empty chain is considered valid.
    """
    if not records:
        return VerifyResult(valid=True, total_records=0)

    expected_prev = GENESIS_HASH

    for idx, record in enumerate(records):
        if record.prev_hash != expected_prev:
            return VerifyResult(
                valid=False,
                total_records=len(records),
                first_invalid_index=idx,
                first_invalid_id=record.id,
                reason=f"prev_hash mismatch at index {idx}: "
                       f"expected {expected_prev[:16]}… got {record.prev_hash[:16]}…",
            )

        recomputed = compute_hash(
            record.prev_hash,
            canonical_json(record.payload_json),
            record.created_at,
        )

        if recomputed != record.curr_hash:
            return VerifyResult(
                valid=False,
                total_records=len(records),
                first_invalid_index=idx,
                first_invalid_id=record.id,
                reason=f"curr_hash mismatch at index {idx} (id={record.id}): "
                       f"stored={record.curr_hash[:16]}… recomputed={recomputed[:16]}…",
            )

        expected_prev = record.curr_hash

    return VerifyResult(valid=True, total_records=len(records))


def build_audit_payload(decision_id: str, request_id: str, decision_type: str,
                        outcome: str, trace: list[str]) -> dict:
    """
    Build the canonical payload that gets hashed into the ledger.
    Must contain ONLY non-PII fields — redacted_context (entity labels) is fine.
    """
    return {
        "decision_id": decision_id,
        "request_id": request_id,
        "decision_type": decision_type,
        "outcome": outcome,
        "trace": trace,
    }
