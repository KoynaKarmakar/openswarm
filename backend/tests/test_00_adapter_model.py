"""
MockBankAdapter + XGBoost fraud model integration tests.
Require seed_data to be generated (generate_and_train.py must have been run).

NOTE: Model tests run in a subprocess to avoid OpenMP/spaCy conflict on Python 3.13
when both XGBoost and spaCy are loaded in the same process (known macOS ARM issue).
"""

import pytest
from app.adapters.mock_adapter import MockBankAdapter


@pytest.fixture(scope="module")
def adapter():
    return MockBankAdapter()


@pytest.fixture(scope="module")
def model():
    # Lazy import — defer loading until after adapter tests complete
    from app.ml.fraud_model import FraudModel
    return FraudModel()


# ── Adapter: customer loading ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adapter_loads_customers(adapter):
    assert len(adapter._customers) == 100


@pytest.mark.asyncio
async def test_adapter_verify_identity_returns_record(adapter):
    cust_id = list(adapter._customers.keys())[0]
    record = await adapter.verify_identity(cust_id)
    assert record.customer_id == cust_id
    assert record.kyc_status in ("VERIFIED", "PENDING", "REJECTED", "EXPIRED")
    assert record.risk_tier in ("A", "B", "C", "D")


@pytest.mark.asyncio
async def test_adapter_did_credential_has_no_pii(adapter):
    cust_id = list(adapter._customers.keys())[0]
    record = await adapter.verify_identity(cust_id)
    cred_str = str(record.did_credential)
    # Credential must not embed raw PII
    assert "pan" not in cred_str.lower()
    assert "aadhaar" not in cred_str.lower()
    assert "phone" not in cred_str.lower()
    assert record.full_name_redacted[-1] == "."  # initials format: "X.Y."


@pytest.mark.asyncio
async def test_adapter_get_account(adapter):
    acc_id = list(adapter._accounts.keys())[0]
    acc = await adapter.get_account(acc_id)
    assert acc.account_id == acc_id
    assert acc.balance >= 0
    assert acc.account_type in ("SAVINGS", "CURRENT", "FIXED_DEPOSIT")


@pytest.mark.asyncio
async def test_adapter_get_transactions(adapter):
    acc_id = list(adapter._txn_by_account.keys())[0]
    txns = await adapter.get_transactions(acc_id, limit=5)
    assert len(txns) <= 5
    for t in txns:
        assert t.amount > 0
        assert t.transaction_type in ("UPI", "NEFT", "RTGS", "IMPS", "ATM", "DEBIT", "CREDIT")


@pytest.mark.asyncio
async def test_adapter_transactions_ordered_newest_first(adapter):
    acc_id = list(adapter._txn_by_account.keys())[0]
    txns = await adapter.get_transactions(acc_id, limit=10)
    if len(txns) > 1:
        for i in range(len(txns) - 1):
            assert txns[i].created_at >= txns[i + 1].created_at


@pytest.mark.asyncio
async def test_adapter_unknown_customer_raises(adapter):
    with pytest.raises(ValueError, match="Customer not found"):
        await adapter.verify_identity("CUST99999")


# ── Fraud model ───────────────────────────────────────────────────────────────

def test_model_low_score_for_normal_transaction(model):
    score = model.score(
        amount=2000.0, hour_of_day=14, day_of_week=2,
        txn_type="UPI", is_geo_mismatch=False,
        velocity_1h=1, amount_zscore=0.2, is_new_merchant=False,
    )
    assert 0.0 <= score <= 1.0
    assert score < 0.5, f"Normal transaction should have low fraud score, got {score}"


def test_model_high_score_for_fraud_pattern(model):
    score = model.score(
        amount=150000.0, hour_of_day=2, day_of_week=6,
        txn_type="RTGS", is_geo_mismatch=True,
        velocity_1h=5, amount_zscore=8.5, is_new_merchant=True,
    )
    assert score > 0.6, f"Fraud-pattern transaction should have high score, got {score}"


def test_model_score_bounded(model):
    for _ in range(10):
        import random
        score = model.score(
            amount=random.uniform(100, 100000),
            hour_of_day=random.randint(0, 23),
            day_of_week=random.randint(0, 6),
            txn_type=random.choice(["UPI", "NEFT", "ATM"]),
            is_geo_mismatch=random.random() > 0.5,
            velocity_1h=random.randint(0, 10),
            amount_zscore=random.uniform(-2, 10),
            is_new_merchant=random.random() > 0.5,
        )
        assert 0.0 <= score <= 1.0, f"Score out of bounds: {score}"


def test_model_metrics_available(model):
    # New metrics schema uses CV/OOF keys instead of train/test split
    metrics = model.metrics
    assert metrics.get("fraud_ratio_pct") == 10.0
    assert metrics.get("total_samples") == 1200
    assert "cv_mean_precision" in metrics or "oof_precision" in metrics
    assert "cv_mean_recall" in metrics or "oof_recall" in metrics
    assert "feature_importances" in metrics
    assert "cv_folds" in metrics
    assert len(metrics["feature_importances"]) == 13  # 8 original + 5 enriched
