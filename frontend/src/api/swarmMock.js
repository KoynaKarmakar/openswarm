// Client-side swarm simulator — lets the Swarm Console run the agents with NO
// backend (for the OpenSwarm canvas / offline demo). Mirrors the real backend
// agents: redaction recognizers, injection guard, Verhoeff, verified-policy KB,
// outcome precedence, and a SHA-256 decision id. Returns the exact shape of
// POST /swarm/decide.

const VD = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
const VP = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,9,1,6,7,4,3,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
function verhoeffValid(num) {
  if (!/^\d+$/.test(num)) return false
  let c = 0
  const r = num.split('').reverse()
  for (let i = 0; i < r.length; i++) c = VD[c][VP[i % 8][parseInt(r[i], 10)]]
  return c === 0
}

const PII = [
  { t: 'IN_PAN', re: /\b[A-Z]{5}[0-9]{4}[A-Z]\b/g },
  { t: 'IN_AADHAAR', re: /\b\d{4}\s?\d{4}\s?\d{4}\b/g },
  { t: 'IN_IFSC', re: /\b[A-Z]{4}0[A-Z0-9]{6}\b/g },
  { t: 'EMAIL_ADDRESS', re: /\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g },
  { t: 'IN_PHONE', re: /\b(?:\+?91[- ]?)?[6-9]\d{9}\b/g },
]
function redact(text) {
  let out = text; const types = []
  for (const p of PII) out = out.replace(p.re, () => { if (!types.includes(p.t)) types.push(p.t); return `<${p.t}>` })
  return { text: out, types }
}

const INJ = [
  { label: 'ignore-previous-instructions', re: /\bignore\s+(?:all\s+|the\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?|rules?)/i },
  { label: 'role-hijack', re: /\byou\s+are\s+now\b|\bact\s+as\s+(?:a\s+|an\s+)?(?:dan|jailbreak)/i },
  { label: 'money-laundering', re: /\blaunder(?:ing)?\b|\bhawala\b|\bstructuring\b/i },
  { label: 'fake-kyc-document', re: /\b(?:fake|forge|forged|fabricate)\b.{0,20}\b(?:aadhaar|aadhar|pan|kyc|identity|document)\b/i },
  { label: 'evade-tax-kyc', re: /\b(?:evade|avoid|dodge|bypass|skip)\b.{0,20}\b(?:tax|taxes|kyc|reporting|audit)\b/i },
]
function detectInjection(t) { return INJ.filter(p => p.re.test(t)) }

const KB = [
  { keys: ['co-lending', 'colending', 'exposure', 'retained', 'share'], policy: 'RBI Co-Lending Model (CLM)',
    text: 'the originating NBFC retains a minimum of 20% of each individual loan, and the bank funds up to 80%' },
  { keys: ['kyc', 're-kyc', 'periodic', 'updation'], policy: 'RBI Master Direction – KYC',
    text: 'periodic KYC updation is required every 2 years for high-risk, 8 years for medium, and 10 years for low-risk customers' },
  { keys: ['fraud', 'red flag', 'red-flag', 'early warning', 'ews', 'velocity'], policy: 'RBI Master Directions on Frauds',
    text: 'accounts triggering early-warning signals such as unusual velocity or geographic mismatch are placed under enhanced monitoring as Red Flagged Accounts' },
  { keys: ['default loss guarantee', 'dlg', 'fldg'], policy: 'RBI Default Loss Guarantee (DLG)',
    text: 'the total DLG cover on a loan portfolio is capped at five percent of the amount of that portfolio' },
  { keys: ['priority sector', 'psl', 'agriculture', 'msme'], policy: 'RBI Priority Sector Lending (PSL)',
    text: 'the Co-Lending Model targets priority-sector categories such as agriculture and MSME' },
  { keys: ['suspicious', 'str', 'ctr', 'money laundering', 'pmla'], policy: 'PMLA — AML reporting (FIU-IND)',
    text: 'a CTR is filed for cash above ten lakh rupees and an STR for any suspicious transaction, irrespective of amount' },
]
function retrieve(q) {
  const s = q.toLowerCase()
  for (const e of KB) if (e.keys.some(k => s.includes(k))) return e
  return null
}

async function sha256hex(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str))
  return Array.prototype.map.call(new Uint8Array(buf), b => ('0' + b.toString(16)).slice(-2)).join('')
}

export async function mockSwarmDecide(message, opts = {}) {
  const { aadhaar, aadhaarOtp } = opts
  const trace = []
  const red = redact(message)
  trace.push(`guardrail: redacted PII [${red.types.join(', ') || 'none'}] entities_masked=${red.types.length}`)

  const base = async (outcome, confidence, extra = {}) => ({
    request_id: 'demo-' + (await sha256hex(message)).slice(0, 8),
    decision_id: (await sha256hex(message + outcome + Date.now())).slice(0, 12),
    outcome, confidence, confidence_score: Math.round(confidence * 1000) / 10,
    redacted_message: red.text, detected_pii_types: red.types.slice().sort(),
    response: null, vc_verification: null, aadhaar_verification: null, trace, _mock: true,
    ...extra,
  })

  // Guardrail: injection / policy-evasion → short-circuit to auditor
  const hits = detectInjection(message)
  if (hits.length) {
    trace.push(`guardrail: BLOCKED ${hits.map(h => h.label).join(', ')} — short-circuit to Auditor`)
    trace.push('auditor: outcome=REJECTED confidence_score=99.0/100 via=guardrail')
    return base('REJECTED', 0.99, { handoff_path: ['guardrail', 'auditor'] })
  }
  trace.push('guardrail: clean — handing off to Knowledge')

  // Knowledge
  const kb = retrieve(message)
  let response, cited = null
  if (kb) { response = `Per the ${kb.policy}, ${kb.text}.`; cited = [kb.policy]; trace.push(`knowledge: grounded via ${kb.policy}`) }
  else { response = 'I cannot verify this.'; trace.push('knowledge: no policy match → "I cannot verify this" (no LLM call)') }

  // Identity & Fraud
  const isFraud = /transfer|velocity|attempts|geo|mismatch|new merchant|8,00,000|800000/i.test(message)
  let identityRejected = false
  let aadhaar_verification = null
  if (aadhaar) {
    const digits = String(aadhaar).replace(/\D/g, '')
    const masked = 'XXXX XXXX ' + digits.slice(-4)
    const ok = verhoeffValid(digits) && (!aadhaarOtp || aadhaarOtp === '123456')
    aadhaar_verification = ok
      ? { ret: 'y', masked_uid: masked, mode: 'demo', err: null }
      : { ret: 'n', masked_uid: masked, mode: 'demo', err: '998', err_text: 'Invalid Aadhaar / OTP' }
    identityRejected = !ok
    trace.push(`identity_fraud: aadhaar ret=${ok ? 'y' : 'n'} ${masked} mode=demo`)
  }
  trace.push(`identity_fraud: kyc=VERIFIED fraud_score=${isFraud ? '0.88' : '0.07'}`)

  // Auditor: outcome precedence (fraud > identity > knowledge)
  let outcome, confidence
  if (isFraud) { outcome = 'REJECTED'; confidence = 0.12 }
  else if (identityRejected) { outcome = 'REJECTED'; confidence = 0.99 }
  else if (response !== 'I cannot verify this.') { outcome = 'APPROVED'; confidence = 0.92 }
  else { outcome = 'NEEDS_REVIEW'; confidence = 0.5 }
  trace.push(`auditor: outcome=${outcome} confidence_score=${Math.round(confidence * 1000) / 10}/100`)

  return base(outcome, confidence, {
    handoff_path: ['guardrail', 'knowledge', 'identity_fraud', 'auditor'],
    response,
    policy_result: cited ? { details: { policies_cited: cited } } : null,
    aadhaar_verification,
  })
}
