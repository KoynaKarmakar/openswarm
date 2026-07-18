# Unauthorized Electronic Banking Transactions (UEBT) Policy — IDBI Bank
*Reference document for VERITAS Fabric policy RAG. Synthetic representation for prototype.*

## 1. Purpose
Establish the process for handling customer complaints of unauthorized electronic banking transactions and define the liability framework and compensation timelines.

## 2. Scope
Applies to all electronic transactions: UPI, NEFT, RTGS, IMPS, debit card, credit card, internet banking, mobile banking.

## 3. Reporting Timeline and Liability

| Reporting Time After Fraud Discovery | Customer Liability |
|--------------------------------------|--------------------|
| Within 3 working days                | Zero liability (bank absorbs full loss) |
| 4–7 working days                     | Up to ₹10,000 (for >₹5L balance accounts: up to ₹25,000) |
| 8–30 working days                    | Up to 50% of transaction amount |
| > 30 working days                    | As per bank's Board-approved policy |

## 4. VERITAS Fraud Agent Rules (hard rules)

```json
[
  {
    "rule_id": "UEBT-001",
    "description": "Flag transaction if geo mismatch detected (transaction location differs from last 5 avg locations by >500km)",
    "condition": {"geo_mismatch": true, "distance_km": {">": 500}},
    "outcome": "FLAGGED",
    "action": "HOLD_AND_NOTIFY_CUSTOMER"
  },
  {
    "rule_id": "UEBT-002",
    "description": "Flag if >3 transactions of similar amount within 10 minutes (velocity check)",
    "condition": {"velocity_10min": {">": 3}, "amount_similarity": {">": 0.9}},
    "outcome": "FLAGGED",
    "action": "REQUIRE_STEP_UP_AUTH"
  },
  {
    "rule_id": "UEBT-003",
    "description": "Auto-reject transaction if fraud_score > 0.85",
    "condition": {"fraud_score": {">": 0.85}},
    "outcome": "REJECTED",
    "action": "BLOCK_AND_ALERT"
  },
  {
    "rule_id": "UEBT-004",
    "description": "Flag for review if fraud_score between 0.6 and 0.85",
    "condition": {"fraud_score": {"between": [0.6, 0.85]}},
    "outcome": "NEEDS_REVIEW",
    "action": "SOFT_BLOCK_NOTIFY"
  }
]
```

## 5. Customer Notification Requirements
- Immediate SMS/email alert on any transaction > ₹5,000
- Alert includes masked account number (last 4 digits only) — raw account number never in notification
- Dispute filing available 24/7 via mobile/internet banking

## 6. Audit Trail Requirements
All UEBT-related decisions must include in the audit ledger:
- fraud_score at time of decision
- which rule fired (e.g. UEBT-003)
- transaction ID (not account number — account number is PII)
- agent trace (memory-hit or LLM path)
