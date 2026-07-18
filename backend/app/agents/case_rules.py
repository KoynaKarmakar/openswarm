"""
Deterministic liability/compensation/SLA derivation for the Case Queue.

Simplification note: seed_data/sample_policies/uebt_policy.md §3 ties
liability tier to how many days the CUSTOMER took to report a fraud.
VERITAS is an automated detection system, not a dispute-intake flow, so
there is no "reporting delay" input here — instead we use the fraud_agent's
own confidence (fraud_score) and which hard rule fired as the proxy: a
rule that auto-blocks confidently (UEBT-003) gets the customer the fastest,
fullest protection; a soft flag needing human review (UEBT-004) is partial
pending confirmation; anything without a fired rule is fully unassessed.
This mirrors the policy's spirit (faster/more certain catch → less customer
liability) without fabricating data the system doesn't have.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class LiabilityOutcome:
    tier: str
    compensation_percent: float
    sla_deadline: datetime


def derive_liability(fraud_score: float | None, rule_id: str | None) -> LiabilityOutcome:
    now = datetime.now(timezone.utc)

    if rule_id == "UEBT-003":
        # Auto-blocked with high confidence (fraud_score > 0.85) — RBI/2017-18/15
        # zero-liability-within-3-days tier: customer is protected immediately.
        return LiabilityOutcome(
            tier="ZERO_LIABILITY",
            compensation_percent=100.0,
            sla_deadline=now + timedelta(hours=48),
        )

    if rule_id == "UEBT-004":
        # Soft-flagged for human review (fraud_score 0.60-0.85) — partial
        # liability pending confirmation, RBI/2017-18/15 4-7 day tier.
        return LiabilityOutcome(
            tier="PARTIAL_LIABILITY",
            compensation_percent=50.0,
            sla_deadline=now + timedelta(hours=120),
        )

    # No hard rule fired but a case was still opened (e.g. NEEDS_REVIEW
    # without a rule_id) — fully unassessed, longest SLA window.
    return LiabilityOutcome(
        tier="UNDER_ASSESSMENT",
        compensation_percent=0.0,
        sla_deadline=now + timedelta(hours=240),
    )
