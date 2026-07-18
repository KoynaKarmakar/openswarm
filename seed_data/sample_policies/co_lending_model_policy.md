# Co-Lending Model (CLM) Policy — IDBI Bank
*Reference document for VERITAS Fabric policy RAG. Synthetic representation for prototype.*

## 1. Purpose
The Co-Lending Model enables IDBI Bank to partner with registered NBFCs to jointly extend credit, particularly to priority sector borrowers. VERITAS Fabric's credential layer enables instant cross-lender KYC and risk-tier sharing, reducing the standard reconciliation window from 2-5 business days to under 2 seconds.

## 2. Eligibility Criteria for Co-Lending

### Borrower Requirements
- Valid KYC with at least one co-lending partner (bank or NBFC)
- PAN verified and linked to Aadhaar
- No default in last 24 months with any CIBIL-reporting institution
- Risk tier must be A, B, or C (D and below require enhanced due diligence)

### NBFC Partner Requirements
- NBFC registered with RBI and in good standing
- Minimum net-owned fund as per current RBI circular
- Co-lending agreement signed with IDBI Bank

## 3. Risk Tier Definitions (used in VERITAS credential)

| Tier | CIBIL Score Range | Loan-to-Income Ratio | Description |
|------|-------------------|----------------------|-------------|
| A    | 750+              | < 3x                 | Prime borrower, fast-track eligible |
| B    | 700–749           | 3x–5x                | Standard borrower |
| C    | 650–699           | 5x–7x                | Subprime, requires additional verification |
| D    | < 650             | > 7x                 | Enhanced due diligence required |

## 4. KYC Sharing Protocol
Under the VERITAS Credential Layer:
- KYC identity proof is represented as a DID-ready verifiable credential
- The credential includes: verified_name (redacted to initials in transit), kyc_status, risk_tier, kyc_verified_at, issuing_institution
- Raw PII (PAN, Aadhaar, address) is NEVER shared cross-lender — only the credential assertion is shared
- The audit ledger records every cross-lender credential assertion with a hash-chain entry

## 5. Decision Rules (hard rules — no LLM needed)

```json
[
  {
    "rule_id": "CLM-001",
    "description": "Approve co-lending fast-track if risk_tier is A and kyc_status is VERIFIED",
    "condition": {"risk_tier": "A", "kyc_status": "VERIFIED"},
    "outcome": "APPROVED_FAST_TRACK",
    "max_loan_amount_multiplier": 5
  },
  {
    "rule_id": "CLM-002",
    "description": "Approve co-lending standard if risk_tier is B or C and kyc_status is VERIFIED",
    "condition": {"risk_tier": ["B", "C"], "kyc_status": "VERIFIED"},
    "outcome": "APPROVED_STANDARD",
    "max_loan_amount_multiplier": 3
  },
  {
    "rule_id": "CLM-003",
    "description": "Flag for enhanced due diligence if risk_tier is D",
    "condition": {"risk_tier": "D"},
    "outcome": "NEEDS_REVIEW",
    "reason": "Risk tier D requires branch-level enhanced due diligence per RBI guidelines"
  },
  {
    "rule_id": "CLM-004",
    "description": "Reject if KYC not verified",
    "condition": {"kyc_status": {"not": "VERIFIED"}},
    "outcome": "REJECTED",
    "reason": "Co-lending requires verified KYC from at least one partner institution"
  }
]
```

## 6. Audit Requirements
Every co-lending eligibility decision must be:
- Written to the VERITAS immutable audit ledger within the same DB transaction as the decision record
- Traceable to: which agent ran, which rule fired (e.g. CLM-001), memory-hit or LLM-path, credential assertion hash
- Retained for minimum 7 years per RBI record-keeping guidelines

## 7. Unauthorized Transaction Protection (cross-reference UEBT Policy)
Co-lending disbursals above ₹10 lakh trigger an automatic fraud score check via the VERITAS fraud agent before release.
