import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Decision(Base):
    """Immutable record of every agent decision — written once, never updated."""

    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False)  # FRAUD_CHECK, IDENTITY, COMPLIANCE, etc.
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)  # APPROVED, REJECTED, FLAGGED, NEEDS_REVIEW
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # trace: which agents ran, rules fired, memory hit/miss, model used — this IS the Explainable AI layer
    trace: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # redacted_context: what was actually sent to LLM (entity-type labels, no raw PII)
    redacted_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
