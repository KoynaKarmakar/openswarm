"""
Outbox pattern for the VERITAS audit ledger.

Guarantee: every Decision gets an audit record, even if the worker crashes.

Write path (in the request handler):
    async with db.begin():
        decision = Decision(...)
        intent  = OutboxIntent(decision_id=decision.id)
        db.add(decision)
        db.add(intent)
    # Both rows committed atomically — no gap between "decision exists" and
    # "intent to log it exists".

Flush path (background asyncio task, restarted on app startup):
    - SELECT ... FOR UPDATE SKIP LOCKED → prevents double-processing if we
      ever run two workers.
    - Reads the last AuditRecord's curr_hash to extend the chain.
    - Writes AuditRecord, marks OutboxIntent DONE — in one transaction.
    - On crash: PENDING intents survive in Postgres and are retried on restart.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ledger.chain import GENESIS_HASH, build_audit_payload, canonical_json, compute_hash
from app.models.audit import AuditRecord, OutboxIntent, OutboxStatus
from app.models.decision import Decision

logger = logging.getLogger("veritas.ledger")

WORKER_INTERVAL_SECONDS = 2
BATCH_SIZE = 50


# ── Write helper (called from request path) ──────────────────────────────────

async def write_decision_with_intent(
    session: AsyncSession,
    *,
    request_id: str,
    decision_type: str,
    outcome: str,
    confidence: float | None,
    trace: list[str],
    redacted_context: str | None,
) -> Decision:
    """
    Write Decision + OutboxIntent in a SINGLE transaction.
    The caller must pass an already-open session; this function does NOT commit —
    it lets the caller commit so the two rows are always atomically paired.

    Usage:
        async with db.begin():
            decision = await write_decision_with_intent(db, ...)
    """
    decision = Decision(
        request_id=request_id,
        decision_type=decision_type,
        outcome=outcome,
        confidence=confidence,
        trace={"agents": trace},
        redacted_context=redacted_context,
    )
    session.add(decision)
    await session.flush()  # populate decision.id without committing

    intent = OutboxIntent(decision_id=decision.id)
    session.add(intent)

    return decision


# ── Outbox flush worker ───────────────────────────────────────────────────────

async def _get_last_hash(session: AsyncSession) -> str:
    result = await session.execute(
        select(AuditRecord.curr_hash)
        .order_by(AuditRecord.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row if row else GENESIS_HASH


async def _flush_batch(session_factory: async_sessionmaker) -> int:
    """Process up to BATCH_SIZE pending intents. Returns number processed."""
    async with session_factory() as session:
        async with session.begin():
            # SKIP LOCKED → safe to run multiple workers in future
            result = await session.execute(
                select(OutboxIntent)
                .where(OutboxIntent.status == OutboxStatus.PENDING)
                .order_by(OutboxIntent.created_at)
                .with_for_update(skip_locked=True)
                .limit(BATCH_SIZE)
            )
            intents = result.scalars().all()

            if not intents:
                return 0

            # Fetch the current chain tail ONCE per batch (inside same txn)
            prev_hash = await _get_last_hash(session)
            processed = 0

            for intent in intents:
                try:
                    intent.status = OutboxStatus.PROCESSING
                    await session.flush()

                    decision = await session.get(Decision, intent.decision_id)
                    if decision is None:
                        logger.error("OutboxIntent %s has no matching Decision — skipping", intent.id)
                        intent.status = OutboxStatus.FAILED
                        intent.error_message = "Decision row not found"
                        continue

                    payload = build_audit_payload(
                        decision_id=str(decision.id),
                        request_id=decision.request_id,
                        decision_type=decision.decision_type,
                        outcome=decision.outcome,
                        trace=decision.trace.get("agents", []),
                    )
                    payload_str = canonical_json(payload)
                    created_at = datetime.now(timezone.utc)
                    created_at_iso = created_at.isoformat()

                    curr_hash = compute_hash(prev_hash, payload_str, created_at_iso)

                    record = AuditRecord(
                        prev_hash=prev_hash,
                        curr_hash=curr_hash,
                        payload_json=payload,
                        created_at=created_at,
                    )
                    session.add(record)

                    intent.status = OutboxStatus.DONE
                    intent.processed_at = created_at

                    # Chain each record to the previous within this batch
                    prev_hash = curr_hash
                    processed += 1

                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to process OutboxIntent %s", intent.id)
                    intent.status = OutboxStatus.FAILED
                    intent.error_message = str(exc)[:500]

            return processed


async def run_outbox_worker(session_factory: async_sessionmaker) -> None:
    """
    Long-running asyncio task started in main.py lifespan.
    Polls Postgres for PENDING outbox intents and flushes them to the ledger.
    Survives transient DB errors — logs and retries after the interval.
    """
    logger.info("Outbox worker started (interval=%ds)", WORKER_INTERVAL_SECONDS)
    while True:
        try:
            processed = await _flush_batch(session_factory)
            if processed:
                logger.info("Outbox: flushed %d intent(s) to audit ledger", processed)
        except Exception:  # noqa: BLE001
            logger.exception("Outbox worker error — will retry in %ds", WORKER_INTERVAL_SECONDS)
        await asyncio.sleep(WORKER_INTERVAL_SECONDS)
