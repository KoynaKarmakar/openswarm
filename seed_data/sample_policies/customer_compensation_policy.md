# Customer Compensation Policy — IDBI Bank
*Reference document for VERITAS Fabric policy RAG. Synthetic representation for prototype.*

## 1. Purpose
Define compensation entitlements when service failures or unauthorized actions result in customer loss, inconvenience, or delay.

## 2. Compensation Schedule

| Failure Type | Compensation | Timeline |
|---|---|---|
| Failed ATM transaction (amount debited, not dispensed) | Reversal + ₹100/day after 5 working days | Within 5 working days |
| Unauthorized UPI transaction (reported within 3 days) | Full reversal, zero liability | Within 10 working days |
| Delayed NEFT/RTGS credit | Interest at repo rate + 2% on delayed amount | Per RBI timeline |
| KYC-related account freeze (bank error) | ₹500 compensation + immediate unfreeze | Within 2 working days |
| Wrong debit due to technical error | Full reversal + ₹100 | Within 5 working days |

## 3. VERITAS Compliance Agent Rules

```json
[
  {
    "rule_id": "COMP-001",
    "description": "Trigger compensation check if transaction flagged FAILED and amount > 0",
    "condition": {"transaction_status": "FAILED", "amount": {">": 0}},
    "outcome": "COMPENSATION_ELIGIBLE",
    "action": "INITIATE_REVERSAL_WORKFLOW"
  },
  {
    "rule_id": "COMP-002",
    "description": "Escalate to branch manager if compensation > ₹10,000",
    "condition": {"compensation_amount": {">": 10000}},
    "outcome": "NEEDS_REVIEW",
    "action": "ESCALATE_TO_MANAGER"
  }
]
```

## 4. Exclusions
- Customer-induced errors (wrong beneficiary added by customer)
- Transactions where OTP was shared by customer (phishing)
- Force majeure events declared by RBI
