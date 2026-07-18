import axios from 'axios'

const BASE = '/api'

// JWT stored in module memory — not localStorage (avoids XSS persistence).
// Cleared on page reload, which is intentional for a banking prototype.
let _token = null

export const setToken = (t) => { _token = t }
export const getToken = () => _token
export const clearToken = () => { _token = null }

const http = axios.create({ baseURL: BASE })

http.interceptors.request.use((cfg) => {
  if (_token) cfg.headers['Authorization'] = `Bearer ${_token}`
  return cfg
})

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      clearToken()
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function login(email, password) {
  const form = new URLSearchParams({ username: email, password })
  const { data } = await http.post('/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  setToken(data.access_token)
  return data
}

// ── Identity ─────────────────────────────────────────────────────────────────

export async function verifyIdentity(customerId) {
  const { data } = await http.post('/identity/verify', { customer_id: customerId })
  return data
}

export async function getCoLendingEligibility(customerId) {
  const { data } = await http.post('/identity/co-lending-eligibility', { customer_id: customerId })
  return data
}

// ── Fraud ─────────────────────────────────────────────────────────────────────

export async function checkFraud(accountId, transactionId = null) {
  const { data } = await http.post('/fraud/check', {
    account_id: accountId,
    transaction_id: transactionId,
  })
  return data
}

// ── Assistant ─────────────────────────────────────────────────────────────────

export async function chat(message, { userId, accountId, requestType } = {}) {
  const { data } = await http.post('/assistant/chat', {
    message,
    user_id: userId || null,
    account_id: accountId || null,
    request_type: requestType || 'ASSISTANT',
  })
  return data
}

// ── Swarm (OpenSwarm 4-agent orchestration) ─────────────────────────────────────

export async function swarmDecide(message, { requestType, userId, accountId, aadhaar, aadhaarOtp, aadhaarName, verifiableCredential } = {}) {
  const { data } = await http.post('/swarm/decide', {
    message,
    request_type: requestType || 'ASSISTANT',
    user_id: userId || null,
    account_id: accountId || null,
    aadhaar: aadhaar || null,
    aadhaar_otp: aadhaarOtp || null,
    aadhaar_name: aadhaarName || null,
    verifiable_credential: verifiableCredential || null,
  })
  return data
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export async function getAuditTrail(limit = 50) {
  const { data } = await http.get('/audit/trail', { params: { limit } })
  return data
}

export async function verifyChain() {
  const { data } = await http.get('/audit/verify')
  return data
}

export async function getDecisionTrace(requestId) {
  const { data } = await http.get(`/audit/decisions/${requestId}`)
  return data
}

export async function getAuditRecordByDecision(decisionId) {
  const { data } = await http.get(`/audit/records/by-decision/${decisionId}`)
  return data
}

// ── Cases ─────────────────────────────────────────────────────────────────────

export async function getCases(status = null) {
  const { data } = await http.get('/cases', { params: status ? { status_filter: status } : {} })
  return data
}

export async function getCase(caseId) {
  const { data } = await http.get(`/cases/${caseId}`)
  return data
}

export async function overrideCase(caseId, action, reason) {
  const { data } = await http.post(`/cases/${caseId}/override`, { action, reason })
  return data
}

// ── Policy citation (live RAG) ──────────────────────────────────────────────────

export async function getPolicyCitation(ruleId) {
  const { data } = await http.get(`/policy/citation/${ruleId}`)
  return data
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function healthCheck() {
  const { data } = await http.get('/health')
  return data
}
