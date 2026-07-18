// Static registry mapping every VERITAS hard-rule id to the policy clause it
// implements, sourced directly from seed_data/sample_policies/*.md.
// This is what the citation chip renders — decision ≠ black box.
export const CITATIONS = {
  'UEBT-001': {
    doc: 'UEBT Policy', section: '§4', ref: 'RBI/2017-18/15',
    refLabel: 'RBI Master Direction — Customer Protection in UEBT',
    text: 'Flag transaction if geo mismatch detected (transaction location differs from last 5 avg locations by >500km). Outcome: FLAGGED, action: hold and notify customer.',
  },
  'UEBT-002': {
    doc: 'UEBT Policy', section: '§4', ref: 'RBI/2017-18/15',
    refLabel: 'RBI Master Direction — Customer Protection in UEBT',
    text: 'Flag if >3 transactions of similar amount within 10 minutes (velocity check). Outcome: FLAGGED, action: require step-up authentication.',
  },
  'UEBT-003': {
    doc: 'UEBT Policy', section: '§4', ref: 'RBI/2017-18/15',
    refLabel: 'RBI Master Direction — Customer Protection in UEBT',
    text: 'Auto-reject transaction if fraud_score > 0.85. Outcome: REJECTED, action: block and alert.',
  },
  'UEBT-004': {
    doc: 'UEBT Policy', section: '§4', ref: 'RBI/2017-18/15',
    refLabel: 'RBI Master Direction — Customer Protection in UEBT',
    text: 'Flag for review if fraud_score is between 0.60 and 0.85. Outcome: NEEDS_REVIEW, action: soft block + notify.',
  },
  'CLM-001': {
    doc: 'Co-Lending Model Policy', section: '§5', ref: 'RBI/DOR/2025-26/139',
    refLabel: 'RBI — Co-Lending Arrangements Directions, 2025',
    text: 'Approve co-lending fast-track if risk_tier is A and kyc_status is VERIFIED. Max loan amount multiplier: 5x.',
  },
  'CLM-002': {
    doc: 'Co-Lending Model Policy', section: '§5', ref: 'RBI/DOR/2025-26/139',
    refLabel: 'RBI — Co-Lending Arrangements Directions, 2025',
    text: 'Approve co-lending standard if risk_tier is B or C and kyc_status is VERIFIED. Max loan amount multiplier: 3x.',
  },
  'CLM-003': {
    doc: 'Co-Lending Model Policy', section: '§5', ref: 'RBI/DOR/2025-26/139',
    refLabel: 'RBI — Co-Lending Arrangements Directions, 2025',
    text: 'Flag for enhanced due diligence if risk_tier is D. Risk tier D requires branch-level enhanced due diligence per RBI guidelines.',
  },
  'CLM-004': {
    doc: 'Co-Lending Model Policy', section: '§4', ref: 'RBI/DOR/2025-26/139',
    refLabel: 'RBI — Co-Lending Arrangements Directions, 2025',
    text: 'Reject if kyc_status is not VERIFIED — valid KYC with at least one co-lending partner is a hard eligibility requirement.',
  },
  'KYC-001': {
    doc: 'KYC & Digital Banking Policy', section: '§3', ref: 'IDBI Bank Policy',
    refLabel: 'Master Direction — Know Your Customer (KYC), RBI',
    text: 'Approve identity if kyc_status is VERIFIED and not expired (kyc_age_days < 730).',
  },
  'KYC-002': {
    doc: 'KYC & Digital Banking Policy', section: '§3', ref: 'IDBI Bank Policy',
    refLabel: 'Master Direction — Know Your Customer (KYC), RBI',
    text: 'Flag for re-KYC if KYC is older than 2 years (kyc_age_days >= 730). Action: trigger re-KYC workflow.',
  },
  'KYC-003': {
    doc: 'KYC & Digital Banking Policy', section: '§3', ref: 'IDBI Bank Policy',
    refLabel: 'Master Direction — Know Your Customer (KYC), RBI',
    text: 'Reject if kyc_status is REJECTED or EXPIRED — valid KYC is required for all banking services.',
  },
  'COMP-001': {
    doc: 'Customer Compensation Policy', section: '§3', ref: 'IDBI Board-Approved Policy',
    refLabel: 'Customer Compensation Policy',
    text: 'Trigger compensation check if transaction is flagged FAILED and amount > 0. Action: initiate reversal workflow.',
  },
  'COMP-002': {
    doc: 'Customer Compensation Policy', section: '§3', ref: 'IDBI Board-Approved Policy',
    refLabel: 'Customer Compensation Policy',
    text: 'Escalate to branch manager if compensation amount > ₹10,000. Outcome: NEEDS_REVIEW.',
  },
}

export function getCitation(ruleId) {
  return CITATIONS[ruleId] ?? null
}

// Pulls every known rule_id out of an explainability trace (or any string list).
const RULE_ID_PATTERN = /\b(UEBT|CLM|KYC|COMP)-\d{3}\b/g

export function extractRuleIds(strings = []) {
  const found = new Set()
  for (const s of strings) {
    if (!s) continue
    const matches = s.match(RULE_ID_PATTERN)
    if (matches) matches.forEach(m => found.add(m))
  }
  return [...found]
}
