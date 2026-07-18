# KYC & Digital Banking Policy — IDBI Bank
*Reference document for VERITAS Fabric policy RAG. Synthetic representation for prototype.*

## 1. KYC Requirements

### Minimum KYC (for basic digital account)
- Valid mobile number linked to Aadhaar
- PAN or Form 60 (if PAN not available)
- Self-declaration of address

### Full KYC (for full banking services)
- Aadhaar-based OTP verification OR video KYC (V-CIP)
- PAN mandatory for accounts > ₹50,000 balance or > ₹2.5L annual credit
- One proof of address (current)

## 2. KYC Re-verification Triggers
- Account dormant for > 12 months
- Change of address or name
- Suspicious transaction pattern
- Co-lending partner request (cross-lender verification)

## 3. VERITAS Identity Agent Rules

```json
[
  {
    "rule_id": "KYC-001",
    "description": "Approve identity if KYC status is VERIFIED and not expired",
    "condition": {"kyc_status": "VERIFIED", "kyc_age_days": {"<": 730}},
    "outcome": "APPROVED",
    "credential_scope": ["basic_identity", "account_access"]
  },
  {
    "rule_id": "KYC-002",
    "description": "Flag for re-KYC if KYC is older than 2 years",
    "condition": {"kyc_age_days": {">=": 730}},
    "outcome": "NEEDS_REVIEW",
    "action": "TRIGGER_REKYC_WORKFLOW"
  },
  {
    "rule_id": "KYC-003",
    "description": "Reject if KYC is REJECTED or EXPIRED",
    "condition": {"kyc_status": {"in": ["REJECTED", "EXPIRED"]}},
    "outcome": "REJECTED",
    "reason": "Valid KYC required for all banking services"
  }
]
```

## 4. DID-Ready Credential Schema
VERITAS issues verifiable credentials conforming to W3C VC Data Model 2.0:

```json
{
  "@context": ["https://www.w3.org/ns/credentials/v2"],
  "type": ["VerifiableCredential", "BankingIdentityCredential"],
  "issuer": "did:idbi:veritas-fabric-v1",
  "credentialSubject": {
    "id": "did:customer:{{uuid}}",
    "kyc_status": "VERIFIED",
    "risk_tier": "A",
    "kyc_verified_at": "{{iso8601}}",
    "kyc_expires_at": "{{iso8601+2years}}",
    "account_type": "SAVINGS",
    "co_lending_eligible": true,
    "issuing_institution": "IDBI_BANK"
  }
}
```
Raw PII (PAN, Aadhaar, DOB, address) is NEVER included in the credential.
The credential is a PROOF OF ATTRIBUTES, not a copy of documents.

## 5. Digital Banking Limits (for compliance agent)

| Service | Daily Limit | Per-Transaction Limit |
|---------|------------|----------------------|
| UPI | ₹1,00,000 | ₹25,000 |
| IMPS | ₹5,00,000 | ₹5,00,000 |
| NEFT | ₹10,00,000 | No limit |
| RTGS | No limit (min ₹2L) | ₹2,00,000 minimum |
