import { useState } from 'react'
import { BadgeCheck, Search, Loader2, AlertTriangle } from 'lucide-react'
import Layout from '../components/Layout'
import Badge from '../components/Badge'
import CredentialCard from '../components/CredentialCard'
import CitationChip from '../components/CitationChip'
import { extractRuleIds } from '../data/citations'
import { verifyIdentity } from '../api/client'

export default function IdentityCredential() {
  const [customerId, setCustomerId] = useState('CUST00001')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleVerify(e) {
    e.preventDefault()
    setLoading(true); setError(''); setResult(null)
    try {
      const res = await verifyIdentity(customerId.trim())
      setResult(res)
    } catch (err) {
      setError(err.response?.data?.detail || 'Verification failed')
    } finally { setLoading(false) }
  }

  return (
    <Layout>
      <div className="px-8 py-6 flex-1 overflow-y-auto">
        <div className="max-w-lg mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-ink-primary flex items-center gap-2">
              <BadgeCheck className="text-brand-400" size={22} /> Identity / Credential
            </h1>
            <p className="text-ink-muted text-sm mt-1">KYC status and decentralized credential issuance state for a customer</p>
          </div>

          <div className="card p-5">
            <form onSubmit={handleVerify} className="flex gap-3 items-end mb-5">
              <div className="flex-1">
                <label className="label">Customer ID</label>
                <input
                  className="input"
                  value={customerId}
                  onChange={e => setCustomerId(e.target.value)}
                  placeholder="CUST00001"
                />
              </div>
              <button type="submit" className="btn-primary" disabled={loading || !customerId.trim()}>
                {loading ? <><Loader2 size={14} className="animate-spin" /> Checking…</> : <><Search size={14} /> Verify</>}
              </button>
            </form>

            {error && (
              <div className="flex items-center gap-2 p-3 mb-4 bg-surface-panelHover border border-hairline rounded-lg text-ink-secondary text-sm">
                <AlertTriangle size={15} className="text-ink-muted" /> {error}
              </div>
            )}

            {result && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-muted">Outcome</span>
                  <Badge value={result.outcome} size="lg" />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-muted">KYC Status</span>
                  <Badge value={result.kyc_status} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-muted">Risk Tier</span>
                  <span className={`text-xs font-bold rounded px-2 py-0.5 font-mono ${
                    result.risk_tier === 'A' ? 'bg-accent-verifiedDim text-accent-verified' :
                    result.risk_tier === 'D' ? 'bg-accent-criticalDim text-accent-critical' :
                    'bg-accent-flaggedDim text-accent-flagged'
                  }`}>
                    Tier {result.risk_tier}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-ink-muted">Co-Lending Eligible</span>
                  <span className={`text-sm font-medium ${result.co_lending_eligible ? 'text-accent-verified' : 'text-ink-muted'}`}>
                    {result.co_lending_eligible ? '✓ Eligible' : '✗ Not eligible'}
                  </span>
                </div>

                <CredentialCard credential={result.did_credential} kycStatus={result.kyc_status} riskTier={result.risk_tier} />

                {extractRuleIds(result.trace).map(r => (
                  <div key={r}>
                    <p className="text-xs text-ink-muted mb-1.5">Policy Rule</p>
                    <CitationChip ruleId={r} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  )
}
