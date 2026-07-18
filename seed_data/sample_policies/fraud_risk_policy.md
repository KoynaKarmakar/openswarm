# Fraud Risk & Transaction Monitoring Policy — IDBI Bank
*Reference document for VERITAS Fabric policy RAG. Synthetic representation for prototype.*

## 1. Real-Time Transaction Monitoring
Every transaction is scored by the VERITAS fraud agent using:
- Transaction velocity (count per 10 min, 1 hr, 24 hr windows)
- Amount z-score (deviation from customer's 90-day average)
- Geographic anomaly (distance from last known location)
- Device fingerprint mismatch (new device + high-value transaction)
- Time-of-day anomaly (unusual hour for this customer)

## 2. Fraud Score Thresholds

| Score Range | Classification | Action |
|---|---|---|
| 0.00 – 0.40 | Low risk | Allow, standard audit log |
| 0.41 – 0.60 | Medium risk | Allow with enhanced logging |
| 0.61 – 0.85 | High risk | Soft block, customer OTP required |
| 0.86 – 1.00 | Critical | Block, alert customer + branch |

## 3. Feature Engineering (for XGBoost model)

| Feature | Description | Weight |
|---|---|---|
| `txn_velocity_10m` | Transactions in last 10 min from same device | High |
| `amount_zscore` | Z-score vs 90-day rolling avg | High |
| `geo_distance_km` | Distance from last transaction location | Medium |
| `is_new_beneficiary` | First time sending to this beneficiary | Medium |
| `hour_of_day` | 0-23, unusual hours score higher | Low |
| `txn_type_mismatch` | Type differs from customer's top 3 types | Medium |

## 4. Model Performance (synthetic test set)
- Dataset: seed_data/synthetic_transactions.json
- Train/test split: 80/20, stratified by fraud label
- Reported on held-out test set only (never on training data)
- Target: precision ≥ 0.90, recall ≥ 0.85

## 5. Cross-lender Fraud Sharing
For co-lending transactions, a fraud risk summary (score + tier, no raw PII)
can be shared with NBFC co-lending partners via the VERITAS credential assertion.
