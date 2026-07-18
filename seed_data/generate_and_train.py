"""
Synthetic banking data generator + XGBoost fraud model trainer.
Run once: python generate_and_train.py

Outputs:
  synthetic_customers.json
  synthetic_accounts.json
  synthetic_transactions.json  (includes pre-computed ML features, now with 5 enriched features)
  fraud_labels.json
  ../backend/app/ml/fraud_model.joblib
  ../backend/app/ml/fraud_model_metrics.json  (cv metrics, feature importances)

Enriched features (joined from accounts + customers at training time):
  balance_ratio    — amount / account_balance, capped at 10.0
  risk_tier_enc    — A→0, B→1, C→2, D→3
  kyc_verified     — 1 if kyc_status=="VERIFIED" else 0
  account_type_enc — SAVINGS→0, CURRENT→1, FIXED_DEPOSIT→2
  is_frozen_acc    — int(is_frozen)
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
BACKEND = HERE.parent / "backend" / "app" / "ml"
BACKEND.mkdir(parents=True, exist_ok=True)

random.seed(42)
np.random.seed(42)

# ── Config ────────────────────────────────────────────────────────────────────
N_CUSTOMERS   = 100
FRAUD_RATIO   = 0.10
N_TRANSACTIONS = 1200

CITIES = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Pune", "Kolkata", "Ahmedabad"]
MERCHANT_NAMES = [
    "BigBasket", "Swiggy", "Zomato", "Amazon", "Flipkart",
    "HPCL Petrol", "Reliance Smart", "IRCTC", "Ola", "Uber",
    "HDFC Mutual Fund", "LIC Premium", "SBI Life", "Tata AIG",
    "Local Kirana", "Medical Store", "D-Mart", "BigBazaar",
]
TXN_TYPES          = ["UPI", "NEFT", "RTGS", "IMPS", "ATM", "DEBIT", "CREDIT"]
RISK_TIER_WEIGHTS  = {"A": 0.40, "B": 0.35, "C": 0.20, "D": 0.05}
KYC_STATUS_WEIGHTS = {"VERIFIED": 0.85, "PENDING": 0.10, "REJECTED": 0.03, "EXPIRED": 0.02}

RISK_TIER_ENC  = {"A": 0, "B": 1, "C": 2, "D": 3}
ACCOUNT_TYPE_ENC = {"SAVINGS": 0, "CURRENT": 1, "FIXED_DEPOSIT": 2}

FEATURE_COLS = [
    "amount", "hour_of_day", "day_of_week", "txn_type_idx",
    "is_geo_mismatch", "velocity_1h", "amount_zscore", "is_new_merchant",
    # enriched
    "balance_ratio", "risk_tier_enc", "kyc_verified", "account_type_enc", "is_frozen_acc",
]


# ── Customer generation ───────────────────────────────────────────────────────

def generate_customers(n: int) -> list[dict]:
    customers = []
    for i in range(n):
        kyc_status = random.choices(
            list(KYC_STATUS_WEIGHTS.keys()),
            weights=list(KYC_STATUS_WEIGHTS.values()),
        )[0]
        risk_tier = random.choices(
            list(RISK_TIER_WEIGHTS.keys()),
            weights=list(RISK_TIER_WEIGHTS.values()),
        )[0]
        verified_days_ago = random.randint(30, 700)
        n_accounts = random.choice([1, 1, 2])
        customer_id = f"CUST{i + 1:05d}"
        customers.append({
            "customer_id": customer_id,
            "full_name_redacted": f"{chr(65 + i % 26)}.{chr(65 + (i // 26) % 26)}.",
            "kyc_status": kyc_status,
            "kyc_verified_at": (
                datetime.now(timezone.utc) - timedelta(days=verified_days_ago)
            ).isoformat() if kyc_status in ("VERIFIED", "EXPIRED") else None,
            "kyc_expires_at": (
                datetime.now(timezone.utc) - timedelta(days=verified_days_ago) + timedelta(days=730)
            ).isoformat() if kyc_status in ("VERIFIED", "EXPIRED") else None,
            "risk_tier": risk_tier,
            "city": random.choice(CITIES),
            "co_lending_eligible": kyc_status == "VERIFIED" and risk_tier in ("A", "B", "C"),
            "account_ids": [f"ACC{i + 1:05d}{j}" for j in range(n_accounts)],
        })
    return customers


# ── Account generation ────────────────────────────────────────────────────────

def generate_accounts(customers: list[dict]) -> list[dict]:
    accounts = []
    acc_types = ["SAVINGS", "SAVINGS", "SAVINGS", "CURRENT", "FIXED_DEPOSIT"]
    for cust in customers:
        for acc_id in cust["account_ids"]:
            balance_base = random.lognormvariate(11, 1.5)
            accounts.append({
                "account_id": acc_id,
                "customer_id": cust["customer_id"],
                "account_number": str(random.randint(10 ** 11, 10 ** 13 - 1)),
                "account_type": random.choice(acc_types),
                "balance": round(balance_base, 2),
                "is_frozen": cust["kyc_status"] == "REJECTED",
                "kyc_status": cust["kyc_status"],
                "home_city": cust["city"],
            })
    return accounts


# ── Transaction generation ────────────────────────────────────────────────────

def generate_transactions(
    accounts: list[dict],
    customers: list[dict],
    n_total: int,
    fraud_ratio: float,
) -> list[dict]:
    n_fraud = int(n_total * fraud_ratio)
    n_legit = n_total - n_fraud

    # Build lookup maps
    acc_map  = {a["account_id"]: a for a in accounts}
    cust_map = {c["customer_id"]: c for c in customers}
    acc_ids  = list(acc_map.keys())

    acc_avg = {a: random.lognormvariate(9, 1) for a in acc_ids}
    acc_std = {a: acc_avg[a] * random.uniform(0.3, 0.8) for a in acc_ids}

    base_date = datetime.now(timezone.utc) - timedelta(days=90)

    def make_txn(is_fraud: bool, idx: int) -> dict:
        acc_id = random.choice(acc_ids)
        acc    = acc_map[acc_id]
        cust   = cust_map[acc["customer_id"]]
        balance = float(acc["balance"])

        ts = base_date + timedelta(
            days=random.randint(0, 89),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )

        if is_fraud:
            amount          = random.uniform(acc_avg[acc_id] * 3, acc_avg[acc_id] * 10)
            hour            = random.choice([0, 1, 2, 3, 22, 23])
            location        = random.choice([c for c in CITIES if c != acc["home_city"]])
            is_geo_mismatch = True
            velocity_1h     = random.randint(3, 8)
            is_new_merchant = random.random() > 0.3
            txn_type        = random.choice(["NEFT", "RTGS", "IMPS"])
        else:
            amount          = max(10, random.lognormvariate(9, 0.8))
            hour            = random.choice(list(range(8, 22)))
            location        = acc["home_city"] if random.random() > 0.1 else random.choice(CITIES)
            is_geo_mismatch = location != acc["home_city"]
            velocity_1h     = random.randint(0, 2)
            is_new_merchant = random.random() > 0.7
            txn_type        = random.choice(TXN_TYPES)

        zscore        = (amount - acc_avg[acc_id]) / max(acc_std[acc_id], 1.0)
        balance_ratio = min(amount / max(balance, 1.0), 10.0)

        return {
            "transaction_id":  f"TXN{idx + 1:07d}",
            "account_id":      acc_id,
            "amount":          round(amount, 2),
            "transaction_type": txn_type,
            "status":          "COMPLETED",
            "merchant_name":   random.choice(MERCHANT_NAMES),
            "location":        location,
            "ip_address":      f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
            "created_at":      ts.isoformat(),
            # Original ML features
            "hour_of_day":     hour,
            "day_of_week":     ts.weekday(),
            "is_geo_mismatch": int(is_geo_mismatch),
            "velocity_1h":     velocity_1h,
            "amount_zscore":   round(zscore, 4),
            "is_new_merchant": int(is_new_merchant),
            "txn_type_idx":    TXN_TYPES.index(txn_type),
            # Enriched features (joined from accounts + customers)
            "balance_ratio":   round(balance_ratio, 4),
            "risk_tier_enc":   RISK_TIER_ENC.get(cust["risk_tier"], 1),
            "kyc_verified":    int(cust["kyc_status"] == "VERIFIED"),
            "account_type_enc": ACCOUNT_TYPE_ENC.get(acc["account_type"], 0),
            "is_frozen_acc":   int(acc["is_frozen"]),
            "is_fraud":        int(is_fraud),
        }

    transactions = []
    for i in range(n_fraud):
        transactions.append(make_txn(True, i))
    for i in range(n_legit):
        transactions.append(make_txn(False, n_fraud + i))

    random.shuffle(transactions)
    return transactions


# ── XGBoost training with 5-fold cross-validation ────────────────────────────

def train_and_save(transactions: list[dict]) -> dict:
    import joblib
    from sklearn.metrics import (
        classification_report, f1_score, precision_score, recall_score, roc_auc_score,
    )
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from xgboost import XGBClassifier

    X = np.array([[t[f] for f in FEATURE_COLS] for t in transactions])
    y = np.array([t["is_fraud"] for t in transactions])

    n_neg = (y == 0).sum()
    n_pos = (y == 1).sum()
    scale_pos_weight = n_neg / max(n_pos, 1)

    # ── 5-fold cross-validation for honest OOF metrics ──────────────────────
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    cv_model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )

    # OOF probability predictions (what each sample looks like as test data)
    oof_probs = cross_val_predict(cv_model, X, y, cv=cv, method="predict_proba")[:, 1]
    oof_preds = (oof_probs >= 0.5).astype(int)

    # Per-fold metrics
    cv_folds = []
    for fold_idx, (train_idx, test_idx) in enumerate(cv.split(X, y)):
        fold_model = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            scale_pos_weight=scale_pos_weight, random_state=42,
            eval_metric="logloss", verbosity=0,
        )
        fold_model.fit(X[train_idx], y[train_idx])
        fold_probs = fold_model.predict_proba(X[test_idx])[:, 1]
        fold_preds = (fold_probs >= 0.5).astype(int)
        cv_folds.append({
            "fold": fold_idx + 1,
            "precision": round(float(precision_score(y[test_idx], fold_preds, zero_division=0)), 4),
            "recall":    round(float(recall_score(y[test_idx], fold_preds, zero_division=0)), 4),
            "f1_score":  round(float(f1_score(y[test_idx], fold_preds, zero_division=0)), 4),
            "auc_roc":   round(float(roc_auc_score(y[test_idx], fold_probs)), 4),
            "test_n":    len(test_idx),
            "test_fraud_n": int(y[test_idx].sum()),
        })

    cv_precisions = [f["precision"] for f in cv_folds]
    cv_recalls    = [f["recall"] for f in cv_folds]
    cv_f1s        = [f["f1_score"] for f in cv_folds]
    cv_aucs       = [f["auc_roc"] for f in cv_folds]

    print(f"\n{'='*60}")
    print("5-Fold Cross-Validation Results")
    print(f"{'='*60}")
    for fold in cv_folds:
        print(f"  Fold {fold['fold']}: precision={fold['precision']:.4f}  "
              f"recall={fold['recall']:.4f}  f1={fold['f1_score']:.4f}  "
              f"auc={fold['auc_roc']:.4f}")
    print(f"{'─'*60}")
    print(f"  Mean:  precision={np.mean(cv_precisions):.4f}±{np.std(cv_precisions):.4f}  "
          f"recall={np.mean(cv_recalls):.4f}±{np.std(cv_recalls):.4f}  "
          f"f1={np.mean(cv_f1s):.4f}±{np.std(cv_f1s):.4f}  "
          f"auc={np.mean(cv_aucs):.4f}±{np.std(cv_aucs):.4f}")

    # ── Full-dataset OOF classification report ───────────────────────────────
    print(f"\n{'─'*60}")
    print("OOF (Out-of-Fold) Classification Report — all 1200 samples:")
    print(classification_report(y, oof_preds, target_names=["Legitimate", "Fraud"]))

    # ── Final model on all data ───────────────────────────────────────────────
    final_model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    final_model.fit(X, y)

    # Feature importances
    importances = final_model.feature_importances_.tolist()
    feature_importances = {col: round(float(imp), 6) for col, imp in zip(FEATURE_COLS, importances)}
    sorted_fi = sorted(feature_importances.items(), key=lambda x: -x[1])

    print(f"\n{'─'*60}")
    print("Feature Importances (final model, gain-based):")
    for feat, imp in sorted_fi:
        bar = "█" * int(imp * 40)
        print(f"  {feat:<22} {imp:.4f}  {bar}")

    model_path = BACKEND / "fraud_model.joblib"
    joblib.dump(final_model, model_path)
    print(f"\n✓ Model saved to {model_path}")

    metrics = {
        "model_type": "XGBoostClassifier",
        "feature_columns": FEATURE_COLS,
        "n_features": len(FEATURE_COLS),
        "total_samples": len(y),
        "fraud_n": int(n_pos),
        "legit_n": int(n_neg),
        "fraud_ratio_pct": round(float(n_pos / len(y) * 100), 2),
        # OOF aggregate metrics
        "oof_precision": round(float(precision_score(y, oof_preds, zero_division=0)), 4),
        "oof_recall":    round(float(recall_score(y, oof_preds, zero_division=0)), 4),
        "oof_f1_score":  round(float(f1_score(y, oof_preds, zero_division=0)), 4),
        "oof_auc_roc":   round(float(roc_auc_score(y, oof_probs)), 4),
        # CV fold-level stats
        "cv_folds": cv_folds,
        "cv_mean_precision": round(float(np.mean(cv_precisions)), 4),
        "cv_std_precision":  round(float(np.std(cv_precisions)), 4),
        "cv_mean_recall":    round(float(np.mean(cv_recalls)), 4),
        "cv_std_recall":     round(float(np.std(cv_recalls)), 4),
        "cv_mean_f1":        round(float(np.mean(cv_f1s)), 4),
        "cv_std_f1":         round(float(np.std(cv_f1s)), 4),
        "cv_mean_auc":       round(float(np.mean(cv_aucs)), 4),
        "cv_std_auc":        round(float(np.std(cv_aucs)), 4),
        # Feature importances
        "feature_importances": feature_importances,
        "top_features": [f for f, _ in sorted_fi[:5]],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_note": (
            "Metrics from 5-fold stratified cross-validation (OOF predictions). "
            "Features include enriched account+customer attributes joined at training time. "
            "Synthetic data with engineered separators — real-world fraud is harder."
        ),
    }

    metrics_path = BACKEND / "fraud_model_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"✓ Metrics saved to {metrics_path}")
    return metrics


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating synthetic customers...")
    customers = generate_customers(N_CUSTOMERS)

    print("Generating synthetic accounts...")
    accounts = generate_accounts(customers)

    print(f"Generating {N_TRANSACTIONS} synthetic transactions ({FRAUD_RATIO * 100:.0f}% fraud)...")
    transactions = generate_transactions(accounts, customers, N_TRANSACTIONS, FRAUD_RATIO)

    n_fraud = sum(t["is_fraud"] for t in transactions)
    fraud_labels = {
        "total_transactions": len(transactions),
        "fraud_count": n_fraud,
        "legit_count": len(transactions) - n_fraud,
        "fraud_ratio_pct": round(n_fraud / len(transactions) * 100, 2),
        "n_customers": len(customers),
        "n_accounts": len(accounts),
        "date_range_days": 90,
        "feature_columns": FEATURE_COLS,
        "n_features": len(FEATURE_COLS),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(HERE / "synthetic_customers.json", "w") as f:
        json.dump(customers, f, indent=2)
    print(f"  → synthetic_customers.json ({len(customers)} records)")

    with open(HERE / "synthetic_accounts.json", "w") as f:
        json.dump(accounts, f, indent=2)
    print(f"  → synthetic_accounts.json ({len(accounts)} records)")

    with open(HERE / "synthetic_transactions.json", "w") as f:
        json.dump(transactions, f, indent=2)
    print(f"  → synthetic_transactions.json ({len(transactions)} records, {n_fraud} fraud)")

    with open(HERE / "fraud_labels.json", "w") as f:
        json.dump(fraud_labels, f, indent=2)
    print(f"  → fraud_labels.json (n={len(transactions)}, {fraud_labels['fraud_ratio_pct']}% fraud)")

    print("\nTraining XGBoost fraud model (13 features, 5-fold CV)...")
    metrics = train_and_save(transactions)

    print(f"\n{'='*60}")
    print("Final Summary:")
    print(f"  Features            : {metrics['n_features']} (8 original + 5 enriched)")
    print(f"  Top features        : {', '.join(metrics['top_features'])}")
    print(f"  CV Mean Precision   : {metrics['cv_mean_precision']:.4f} ± {metrics['cv_std_precision']:.4f}")
    print(f"  CV Mean Recall      : {metrics['cv_mean_recall']:.4f} ± {metrics['cv_std_recall']:.4f}")
    print(f"  CV Mean AUC-ROC     : {metrics['cv_mean_auc']:.4f} ± {metrics['cv_std_auc']:.4f}")
    print(f"  OOF AUC-ROC         : {metrics['oof_auc_roc']:.4f}")
    print(f"  Total samples       : {metrics['total_samples']} ({metrics['fraud_ratio_pct']}% fraud)")
    print("=" * 60)
