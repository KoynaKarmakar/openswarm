// Backend client for the standalone Swarm Console — talks to the REAL FastAPI
// backend (POST /swarm/decide, /audit/*, /fraud/check). Bearer-token auth via
// the demo login. Every tab uses these when connected; falls back to the
// in-browser engine otherwise.

async function req(base, path, { method = 'GET', token, body, form } = {}) {
  const headers = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  let payload
  if (form) { headers['Content-Type'] = 'application/x-www-form-urlencoded'; payload = new URLSearchParams(form).toString() }
  else if (body) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  const res = await fetch(`${base.replace(/\/$/, '')}${path}`, { method, headers, body: payload })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try { const j = await res.json(); if (j.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

export async function login(base, email = 'demo@idbi.bank', password = 'demo1234') {
  const data = await req(base, '/auth/token', { method: 'POST', form: { username: email, password } })
  return data.access_token
}

export async function health(base) {
  return req(base, '/health')
}

// POST /swarm/decide → { outcome, confidence_score, redacted_message,
//   detected_pii_types, response, handoff_path, trace, vc_verification,
//   aadhaar_verification, decision_id, request_id }
export async function decide(conn, { message, requestType, aadhaar, otp }) {
  return req(conn.base, '/swarm/decide', {
    method: 'POST', token: conn.token,
    body: {
      message,
      request_type: requestType || 'ASSISTANT',
      aadhaar: aadhaar || null,
      aadhaar_otp: otp || null,
    },
  })
}

// GET /audit/trail → [{ id, prev_hash, curr_hash, outcome, confidence, trace, created_at, ... }]
export async function auditTrail(conn, limit = 50) {
  return req(conn.base, `/audit/trail?limit=${limit}`, { token: conn.token })
}

// GET /audit/verify → { valid, records_checked, break_at_index, break_reason }
export async function auditVerify(conn) {
  return req(conn.base, '/audit/verify', { token: conn.token })
}

// POST /fraud/check → { outcome, fraud_score, confidence, rule_id, transactions_checked, trace, health_score }
export async function fraudCheck(conn, accountId) {
  return req(conn.base, '/fraud/check', { method: 'POST', token: conn.token, body: { account_id: accountId } })
}
