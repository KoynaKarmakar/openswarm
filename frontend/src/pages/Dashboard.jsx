import { useState } from 'react'
import { User, TrendingUp, Search, Loader2, AlertTriangle } from 'lucide-react'
import Layout from '../components/Layout'
import Badge from '../components/Badge'
import TracePanel from '../components/TracePanel'
import CitationChip from '../components/CitationChip'
import CredentialCard from '../components/CredentialCard'
import { verifyIdentity, checkFraud } from '../api/client'

export default function Dashboard() {
  const [customerId, setCustomerId] = useState('CUST00001')
  const [accountId, setAccountId]   = useState('ACC000010')
  const [idResult, setIdResult]     = useState(null)
  const [fraudResult, setFraudResult] = useState(null)
  const [loadingId, setLoadingId]   = useState(false)
  const [loadingFraud, setLoadingFraud] = useState(false)
  const [error, setError]           = useState('')

  async function handleVerify(e) {
    e.preventDefault()
    setLoadingId(true); setError(''); setIdResult(null)
    try {
      const res = await verifyIdentity(customerId)
      setIdResult(res)
    } catch (err) {
      setError(err.response?.data?.detail || 'Identity check failed')
    } finally { setLoadingId(false) }
  }

  async function handleFraud(e) {
    e.preventDefault()
    setLoadingFraud(true); setError(''); setFraudResult(null)
    try {
      const res = await checkFraud(accountId)
      setFraudResult(res)
    } catch (err) {
      setError(err.response?.data?.detail || 'Fraud check failed')
    } finally { setLoadingFraud(false) }
  }

  return (
    <Layout>
      <div className="px-8 py-6 flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-ink-primary">Banking Dashboard</h1>
            <p className="text-ink-muted text-sm mt-1">Identity verification & fraud risk — every check is audit-logged</p>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 mb-5 bg-surface-panelHover border border-hairline rounded-lg text-ink-secondary text-sm">
              <AlertTriangle size={15} className="text-ink-muted" /> {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-5">
            {/* Identity Check */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <User size={18} className="text-brand-600" />
                <h2 className="font-semibold text-ink-primary">Identity Verification</h2>
              </div>

              <form onSubmit={handleVerify} className="space-y-3 mb-4">
                <div>
                  <label className="label">Customer ID</label>
                  <input className="input" value={customerId} onChange={e => setCustomerId(e.target.value)} placeholder="CUST00001" />
                </div>
                <button type="submit" className="btn-primary w-full justify-center" disabled={loadingId}>
                  {loadingId ? <><Loader2 size={14} className="animate-spin" /> Verifying…</> : <><Search size={14} /> Verify Identity</>}
                </button>
              </form>

              {idResult && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ink-muted">Outcome</span>
                    <Badge value={idResult.outcome} size="lg" />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ink-muted">KYC Status</span>
                    <Badge value={idResult.kyc_status} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ink-muted">Risk Tier</span>
                    <span className={`px-2 py-0.5 text-xs font-bold rounded font-mono ${
                      idResult.risk_tier === 'A' ? 'bg-accent-verifiedDim text-accent-verified' :
                      idResult.risk_tier === 'D' ? 'bg-accent-criticalDim text-accent-critical' :
                      'bg-accent-flaggedDim text-accent-flagged'
                    }`}>Tier {idResult.risk_tier}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ink-muted">Co-Lending</span>
                    <span className={`text-sm font-medium ${idResult.co_lending_eligible ? 'text-accent-verified' : 'text-ink-muted'}`}>
                      {idResult.co_lending_eligible ? '✓ Eligible' : '✗ Not eligible'}
                    </span>
                  </div>

                  {/* DID Credential preview */}
                  <div className="mt-3">
                    <CredentialCard
                      credential={idResult.did_credential}
                      kycStatus={idResult.kyc_status}
                      riskTier={idResult.risk_tier}
                    />
                  </div>

                  <TracePanel trace={idResult.trace} />
                </div>
              )}
            </div>

            {/* Fraud Check */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={18} className="text-brand-600" />
                <h2 className="font-semibold text-ink-primary">Fraud Risk Check</h2>
              </div>

              <form onSubmit={handleFraud} className="space-y-3 mb-4">
                <div>
                  <label className="label">Account ID</label>
                  <input className="input" value={accountId} onChange={e => setAccountId(e.target.value)} placeholder="CUST000010" />
                </div>
                <button type="submit" className="btn-primary w-full justify-center" disabled={loadingFraud}>
                  {loadingFraud ? <><Loader2 size={14} className="animate-spin" /> Analysing…</> : <><Search size={14} /> Check Fraud Risk</>}
                </button>
              </form>

              {fraudResult && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ink-muted">Outcome</span>
                    <Badge value={fraudResult.outcome} size="lg" />
                  </div>

                  {fraudResult.fraud_score !== null && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-ink-muted">Fraud Score</span>
                        <span className={`text-sm font-semibold font-mono ${
                          fraudResult.fraud_score > 0.85 ? 'text-accent-critical' :
                          fraudResult.fraud_score > 0.60 ? 'text-accent-flagged' : 'text-accent-verified'
                        }`}>{(fraudResult.fraud_score * 100).toFixed(1)}%</span>
                      </div>
                      <div className="h-2 bg-hairline rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            fraudResult.fraud_score > 0.85 ? 'bg-accent-critical' :
                            fraudResult.fraud_score > 0.60 ? 'bg-accent-flagged' : 'bg-accent-verified'
                          }`}
                          style={{ width: `${(fraudResult.fraud_score * 100).toFixed(1)}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-ink-muted mt-1">
                        <span>Low</span><span>Medium</span><span>High</span>
                      </div>
                    </div>
                  )}

                  {fraudResult.rule_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-ink-muted">Policy Rule</span>
                      <CitationChip ruleId={fraudResult.rule_id} />
                    </div>
                  )}

                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ink-muted">Transactions Checked</span>
                    <span className="text-sm text-ink-primary font-medium">{fraudResult.transactions_checked}</span>
                  </div>

                  <TracePanel trace={fraudResult.trace} />
                </div>
              )}
            </div>
          </div>

          {/* System info footer */}
          <div className="mt-5 p-4 bg-surface-panel border border-hairline rounded-xl">
            <p className="text-xs text-ink-muted">
              <span className="font-semibold text-ink-primary">VERITAS Fabric</span> — Every decision above is written to an immutable hash-chain audit ledger.
              View the full trail in <a href="/audit" className="underline font-medium text-brand-400">Audit Timeline</a>.
              Prototype uses synthetic data with mock IDBI adapters.
            </p>
          </div>
        </div>
      </div>
    </Layout>
  )
}
