from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.ledger.chain import ChainRecord, VerifyResult, canonical_json, compute_hash, verify_chain
from app.models.audit import AuditRecord
from app.models.decision import Decision

router = APIRouter(prefix="/audit", tags=["audit"])


class HashChainEntryResponse(BaseModel):
    found: bool
    id: str | None = None
    prev_hash: str | None = None
    curr_hash: str | None = None
    payload: dict | None = None
    created_at: datetime | None = None
    hash_valid: bool | None = None
    note: str | None = None


class AuditRecordResponse(BaseModel):
    id: str
    prev_hash: str
    curr_hash: str
    payload: dict
    created_at: datetime
    # Flattened payload fields for direct frontend access
    decision_type: str | None = None
    outcome: str | None = None
    confidence: float | None = None
    trace: list[str] = []
    request_id: str | None = None


class ChainVerifyResponse(BaseModel):
    valid: bool
    # Fields named to match frontend expectations
    records_checked: int
    break_at_index: int | None = None
    break_reason: str | None = None


class DecisionTraceResponse(BaseModel):
    decision_id: str
    request_id: str
    decision_type: str
    outcome: str
    confidence: float | None
    trace: list[str]
    redacted_context: str | None
    created_at: datetime


@router.get("/trail", response_model=list[AuditRecordResponse])
async def get_audit_trail(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Return the most recent audit ledger records, newest first."""
    result = await db.execute(
        select(AuditRecord).order_by(AuditRecord.created_at.desc()).limit(limit)
    )
    records = result.scalars().all()
    return [
        AuditRecordResponse(
            id=str(r.id),
            prev_hash=r.prev_hash,
            curr_hash=r.curr_hash,
            payload=r.payload_json,
            created_at=r.created_at,
            decision_type=r.payload_json.get("decision_type"),
            outcome=r.payload_json.get("outcome"),
            confidence=r.payload_json.get("confidence"),
            trace=r.payload_json.get("trace", []),
            request_id=r.payload_json.get("request_id"),
        )
        for r in records
    ]


@router.get("/verify", response_model=ChainVerifyResponse)
async def verify_audit_chain(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Walk the entire hash chain and verify integrity.
    Returns where the chain first breaks, if at all.
    This is a live-demo endpoint — the frontend Verify button calls this.
    """
    result = await db.execute(
        select(AuditRecord).order_by(AuditRecord.created_at.asc())
    )
    db_records = result.scalars().all()

    chain_records = [
        ChainRecord(
            id=str(r.id),
            prev_hash=r.prev_hash,
            curr_hash=r.curr_hash,
            payload_json=r.payload_json,
            created_at=r.created_at.isoformat(),
        )
        for r in db_records
    ]

    result_obj: VerifyResult = verify_chain(chain_records)
    return ChainVerifyResponse(
        valid=result_obj.valid,
        records_checked=result_obj.total_records,
        break_at_index=result_obj.first_invalid_index,
        break_reason=result_obj.reason,
    )


@router.get("/decisions/{request_id}", response_model=list[DecisionTraceResponse])
async def get_decision_trace(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Return all decisions for a request_id, including the full agent trace."""
    result = await db.execute(
        select(Decision)
        .where(Decision.request_id == request_id)
        .order_by(Decision.created_at.desc())
    )
    decisions = result.scalars().all()

    if not decisions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No decisions found for this request_id")

    return [
        DecisionTraceResponse(
            decision_id=str(d.id),
            request_id=d.request_id,
            decision_type=d.decision_type,
            outcome=d.outcome,
            confidence=d.confidence,
            trace=d.trace.get("agents", []),
            redacted_context=d.redacted_context,
            created_at=d.created_at,
        )
        for d in decisions
    ]


@router.get("/records/by-decision/{decision_id}", response_model=HashChainEntryResponse)
async def get_audit_record_by_decision(
    decision_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Look up the hash-chain entry for a specific decision_id — powers the
    "hash-chain entry viewer" in the Case Queue's Audit/Citation pane.

    The AuditRecord is written asynchronously by the outbox worker (up to
    WORKER_INTERVAL_SECONDS after the decision), so this can legitimately
    return found=False for a few seconds right after a decision is made —
    that's the outbox pattern working as intended, not a bug.
    """
    result = await db.execute(
        select(AuditRecord).where(
            AuditRecord.payload_json["decision_id"].astext == decision_id
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        return HashChainEntryResponse(
            found=False,
            note="Not yet written to the ledger — the outbox worker flushes every few seconds.",
        )

    recomputed = compute_hash(
        record.prev_hash, canonical_json(record.payload_json), record.created_at.isoformat(),
    )

    return HashChainEntryResponse(
        found=True,
        id=str(record.id),
        prev_hash=record.prev_hash,
        curr_hash=record.curr_hash,
        payload=record.payload_json,
        created_at=record.created_at,
        hash_valid=(recomputed == record.curr_hash),
    )
