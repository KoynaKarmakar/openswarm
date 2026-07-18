"""
XGBoost fraud model wrapper — loaded once at startup, used by fraud_agent.

Features: 8 original + 5 enriched account/customer features (13 total).
Evaluation: 5-fold stratified cross-validation on synthetic data.

See backend/app/ml/fraud_model_metrics.json for CV metrics and feature importances.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np

logger = logging.getLogger("veritas.ml")

HERE = Path(__file__).parent

FEATURE_COLS = [
    "amount",
    "hour_of_day",
    "day_of_week",
    "txn_type_idx",
    "is_geo_mismatch",
    "velocity_1h",
    "amount_zscore",
    "is_new_merchant",
    # Enriched account + customer features
    "balance_ratio",
    "risk_tier_enc",
    "kyc_verified",
    "account_type_enc",
    "is_frozen_acc",
]

TXN_TYPE_IDX = {
    "UPI": 0, "NEFT": 1, "RTGS": 2, "IMPS": 3,
    "ATM": 4, "DEBIT": 5, "CREDIT": 6,
}

RISK_TIER_ENC    = {"A": 0, "B": 1, "C": 2, "D": 3}
ACCOUNT_TYPE_ENC = {"SAVINGS": 0, "CURRENT": 1, "FIXED_DEPOSIT": 2}


class FraudModel:
    def __init__(self):
        import joblib
        model_path = HERE / "fraud_model.joblib"
        if not model_path.exists():
            raise FileNotFoundError(
                f"Fraud model not found at {model_path}. "
                "Run seed_data/generate_and_train.py first."
            )
        self._model = joblib.load(model_path)

        metrics_path = HERE / "fraud_model_metrics.json"
        if metrics_path.exists():
            with open(metrics_path) as f:
                self.metrics = json.load(f)
        else:
            self.metrics = {}

        logger.info(
            "Fraud model loaded — CV AUC=%.4f precision=%.4f recall=%.4f (%d features, synthetic data)",
            self.metrics.get("cv_mean_auc", self.metrics.get("auc_roc", 0)),
            self.metrics.get("cv_mean_precision", self.metrics.get("precision", 0)),
            self.metrics.get("cv_mean_recall", self.metrics.get("recall", 0)),
            len(FEATURE_COLS),
        )

    def score(
        self,
        amount: float,
        hour_of_day: int,
        day_of_week: int,
        txn_type: str,
        is_geo_mismatch: bool,
        velocity_1h: int,
        amount_zscore: float,
        is_new_merchant: bool,
        # Enriched features — default to safe/moderate values
        balance_ratio: float = 0.0,
        risk_tier_enc: int = 1,         # B tier
        kyc_verified: int = 1,          # assume verified
        account_type_enc: int = 0,      # SAVINGS
        is_frozen_acc: int = 0,         # not frozen
    ) -> float:
        """Return fraud probability in [0.0, 1.0]."""
        features = np.array([[
            amount,
            hour_of_day,
            day_of_week,
            TXN_TYPE_IDX.get(txn_type, 5),
            int(is_geo_mismatch),
            velocity_1h,
            amount_zscore,
            int(is_new_merchant),
            float(balance_ratio),
            int(risk_tier_enc),
            int(kyc_verified),
            int(account_type_enc),
            int(is_frozen_acc),
        ]])
        prob = self._model.predict_proba(features)[0][1]
        return float(round(prob, 4))

    def feature_importances(self) -> dict[str, float]:
        return self.metrics.get("feature_importances", {})


@lru_cache(maxsize=1)
def get_fraud_model() -> FraudModel:
    return FraudModel()
