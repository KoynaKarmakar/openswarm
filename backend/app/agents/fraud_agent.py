from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.adapters.base import BankAdapter
from app.adapters.mock_adapter import MockBankAdapter
from app.agents.state import AgentResult, VeritasState
from app.ml.fraud_model import ACCOUNT_TYPE_ENC, RISK_TIER_ENC, get_fraud_model

logger = logging.getLogger("veritas.fraud")

_REJECT_THRESHOLD = 0.85
_FLAG_THRESHOLD = 0.60


def _compute_zscore(amount: float, mean: float, std: float) -> float:
    return (amount - mean) / max(std, 1.0)


def _compute_health_score(
    *,
    confidence: float,
    transactions_checked: int,
    rule_id: str | None,
    account_info_available: bool,
    customer_info_available: bool,
    precomputed_features_used: bool,
) -> dict:
    """
    Aggregates every signal the fraud_agent has about *how trustworthy its own
    decision is* into one 0-100 explainability health score, so the UI can
    surface a single number instead of forcing users to parse raw trace text.
    """
    model_confidence = round(confidence * 100, 1)

    data_completeness = round(min(transactions_checked / 30, 1.0) * 100, 1)

    sources_available = sum([
        account_info_available,
        customer_info_available,
        precomputed_features_used,
    ])
    feature_reliability = round((sources_available / 3) * 100, 1)

    # A deterministic UEBT rule firing is fully explainable; a pure ML
    # decision (no hard rule) is inherently less transparent.
    rule_transparency = 100.0 if rule_id else 65.0

    overall = round(
        0.35 * model_confidence
        + 0.25 * data_completeness
        + 0.25 * feature_reliability
        + 0.15 * rule_transparency,
        1,
    )

    return {
        "overall": overall,
        "components": {
            "model_confidence": {
                "score": model_confidence,
                "weight": 0.35,
                "label": "Model Confidence",
                "description": "1 - fraud_score, from the XGBoost model output.",
            },
            "data_completeness": {
                "score": data_completeness,
                "weight": 0.25,
                "label": "Data Completeness",
                "description": f"{transactions_checked}/30 recent transactions available.",
            },
            "feature_reliability": {
                "score": feature_reliability,
                "weight": 0.25,
                "label": "Feature Reliability",
                "description": f"{sources_available}/3 enriched data sources found "
                                "(account, customer, precomputed transaction features); "
                                "missing sources fall back to safe defaults.",
            },
            "rule_transparency": {
                "score": rule_transparency,
                "weight": 0.15,
                "label": "Rule Transparency",
                "description": (
                    f"Deterministic UEBT rule {rule_id} fired." if rule_id
                    else "No hard rule fired — outcome is ML-only."
                ),
            },
        },
    }


async def fraud_node(state: VeritasState, adapter: BankAdapter) -> dict:
    """
    Score the transaction for fraud risk using the XGBoost model.
    Features are engineered from recent transaction history via the BankAdapter.
    Falls back gracefully if the model or adapter is unavailable.
    """
    account_id = state.get("account_id") or state.get("extra_context", {}).get("account_id")
    transaction_id = state.get("transaction_id") or state.get("extra_context", {}).get("transaction_id")

    if not account_id:
        return {
            "fraud_result": AgentResult(
                outcome="APPROVED",
                confidence=1.0,
                details={"note": "no account_id — fraud check skipped"},
            ),
            "trace": ["fraud_agent: skipped — no account_id"],
        }

    try:
        transactions = await adapter.get_transactions(account_id, limit=30)
    except Exception as exc:
        logger.exception("Fraud agent could not fetch transactions for %s", account_id)
        return {
            "fraud_result": AgentResult(
                outcome="NEEDS_REVIEW", confidence=0.0, details={"error": str(exc)},
            ),
            "trace": [f"fraud_agent: error fetching transactions — {exc}"],
        }

    if not transactions:
        return {
            "fraud_result": AgentResult(
                outcome="APPROVED", confidence=0.9, details={"note": "no transaction history"},
            ),
            "trace": ["fraud_agent: no history — low risk assumed"],
        }

    # Fetch enriched account + customer context for the 5 new features
    balance_ratio    = 0.0
    risk_tier_enc    = 1   # default: B tier
    kyc_verified     = 1   # default: assume verified
    account_type_enc = 0   # default: SAVINGS
    is_frozen_acc    = 0

    account_info_available = False
    try:
        account_info     = await adapter.get_account(account_id)
        account_type_enc = ACCOUNT_TYPE_ENC.get(account_info.account_type, 0)
        is_frozen_acc    = int(account_info.is_frozen)
        account_balance  = account_info.balance
        account_info_available = True
    except Exception:
        account_balance = 1.0

    customer_info_available = False
    if isinstance(adapter, MockBankAdapter):
        cust = adapter.get_customer_for_account(account_id)
        if cust:
            risk_tier_enc = RISK_TIER_ENC.get(cust.get("risk_tier", "B"), 1)
            kyc_verified  = int(cust.get("kyc_status") == "VERIFIED")
            customer_info_available = True

    # If a specific transaction ID was provided, score that one.
    # Otherwise score the most recent transaction.
    target_txn = None
    if transaction_id and isinstance(adapter, MockBankAdapter):
        target_txn = adapter.get_raw_transaction(transaction_id)

    # Use pre-computed features if available (from synthetic data).
    # In production, engineer features in real-time from raw transaction fields.
    precomputed_features_used = bool(target_txn and "hour_of_day" in target_txn)
    if precomputed_features_used:
        raw    = target_txn
        amount = float(raw["amount"])
        stats  = adapter.get_account_stats(account_id) if isinstance(adapter, MockBankAdapter) else {"mean_amount": amount, "std_amount": amount * 0.5}
        zscore = raw.get("amount_zscore") or _compute_zscore(amount, stats["mean_amount"], stats["std_amount"])
        balance_ratio = raw.get("balance_ratio") or min(amount / max(account_balance, 1.0), 10.0)

        score = get_fraud_model().score(
            amount=amount,
            hour_of_day=raw.get("hour_of_day", 12),
            day_of_week=raw.get("day_of_week", 2),
            txn_type=raw.get("transaction_type", "UPI"),
            is_geo_mismatch=bool(raw.get("is_geo_mismatch", False)),
            velocity_1h=int(raw.get("velocity_1h", 1)),
            amount_zscore=float(zscore),
            is_new_merchant=bool(raw.get("is_new_merchant", False)),
            balance_ratio=float(balance_ratio),
            risk_tier_enc=risk_tier_enc,
            kyc_verified=kyc_verified,
            account_type_enc=account_type_enc,
            is_frozen_acc=is_frozen_acc,
        )
    else:
        # Fallback: use the most recent transaction's stored fraud_score
        latest = transactions[0]
        score = latest.fraud_score if latest.fraud_score is not None else 0.1

    # Apply UEBT policy thresholds
    if score > _REJECT_THRESHOLD:
        outcome, rule = "REJECTED", "UEBT-003"
    elif score > _FLAG_THRESHOLD:
        outcome, rule = "FLAGGED", "UEBT-004"
    else:
        outcome, rule = "APPROVED", None

    confidence = round(1.0 - score, 4)
    health_score = _compute_health_score(
        confidence=confidence,
        transactions_checked=len(transactions),
        rule_id=rule,
        account_info_available=account_info_available,
        customer_info_available=customer_info_available,
        precomputed_features_used=precomputed_features_used,
    )

    return {
        "fraud_result": AgentResult(
            outcome=outcome,
            confidence=confidence,
            rule_id=rule,
            details={
                "fraud_score": round(score, 4),
                "transactions_checked": len(transactions),
                "model": "xgboost_v1",
                "health_score": health_score,
            },
        ),
        "trace": [
            f"fraud_agent: score={score:.3f} threshold_reject={_REJECT_THRESHOLD} "
            f"outcome={outcome} rule={rule} model=xgboost_13feat "
            f"risk_tier_enc={risk_tier_enc} kyc_verified={kyc_verified} balance_ratio={balance_ratio:.3f}",
            f"fraud_agent: explainability_health_score={health_score['overall']}/100 "
            f"(model_confidence={health_score['components']['model_confidence']['score']}, "
            f"data_completeness={health_score['components']['data_completeness']['score']}, "
            f"feature_reliability={health_score['components']['feature_reliability']['score']}, "
            f"rule_transparency={health_score['components']['rule_transparency']['score']})",
        ],
    }
