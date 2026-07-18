import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CaseStatus(str, PyEnum):
    UNDER_REVIEW = "UNDER_REVIEW"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    ESCALATED = "ESCALATED"
    OVERRIDDEN = "OVERRIDDEN"


class CaseType(str, PyEnum):
    FRAUD = "FRAUD"
    DISPUTE = "DISPUTE"


class OverrideAction(str, PyEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class Case(Base):
    """
    A working item for a compliance officer — created automatically when a
    fraud check resolves to FLAGGED/NEEDS_REVIEW. Distinct from Decision
    (which is the immutable per-request record); a Case is the mutable
    "queue item" wrapping one, so it can carry status/SLA/override state.
    """

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    case_type: Mapped[CaseType] = mapped_column(Enum(CaseType), default=CaseType.FRAUD, nullable=False)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.UNDER_REVIEW, nullable=False, index=True)

    fraud_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    liability_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    compensation_percent: Mapped[float] = mapped_column(Float, nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    decision_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    trace: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )


class CaseOverride(Base):
    """
    Human-in-the-loop record: a compliance officer accepting or rejecting the
    automated decision on a Case, with a mandatory reason. Written alongside
    a hash-chained audit entry (decision_type=CASE_OVERRIDE) so overrides are
    just as tamper-evident as the automated decisions they act on.
    """

    __tablename__ = "case_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    officer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    officer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[OverrideAction] = mapped_column(Enum(OverrideAction), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
