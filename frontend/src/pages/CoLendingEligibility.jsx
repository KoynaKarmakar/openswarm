import { useState } from 'react'
import { Handshake, Search, Loader2, AlertTriangle, ArrowRight, ArrowLeft, CheckCircle2, Building2 } from 'lucide-react'
import Layout from '../components/Layout'
import Badge from '../components/Badge'
import CredentialCard from '../components/CredentialCard'
import CitationChip from '../components/CitationChip'
import { getCoLendingEligibility } from '../api/client'

const STEPS = [
  { n: 1, label: 'Originating RE Verifies' },
  { n: 2, label: 'Partner RE Reuses Credential' },
  { n: 3, label: 'Eligibility Decision' },
]

function StepIndicator({ step }) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {STEPS.map((s, i) => (
        <div key={s.n} className="flex items-center gap-2 flex-1">
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold font-mono border ${
              step === s.n ? 'bg-brand-500/20 border-brand-500 text-brand-300'
              : step > s.n ? 'bg-accent-verifiedDim border-accent-verified text-accent-verified'
              : 'border-hairline text-ink-muted'
            }`}>
              {step > s.n ? <CheckCircle2 size={14} /> : s.n}
            </div>
            <span className={`text-xs hidden md:inline ${step === s.n ? 'text-ink-primary font-medium' : 'text-ink-muted'}`}>{s.label}</span>
          </div>
          {i < STEPS.length - 1 && <div className={`h-px flex-1 ${step > s.n ? 'bg-accent-verified' : 'bg-hairline'}`} />}
        </div>
      ))}
    </div>
  )
}

export default function CoLendingEligibility() {
  const [step, setStep] = useState(1)
  const [customerId, setCustomerId] = useState('CUST00001')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleVerify(e) {
    e.preventDefault()
    setLoading(true); setError(''); setResult(null)
    try {
      const res = await getCoLendingEligibility(customerId.trim())
      setResult(res)
      setStep(2)
    } catch (err) {
      setError(err.response?.data?.detail || 'Verification failed')
    } finally { setLoading(false) }
  }

  function reset() {
    setStep(1); setResult(null); setError('')
  }

  return (
    <Layout>
      <div className="px-8 py-6 flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-ink-primary flex items-center gap-2">
              <Handshake className="text-brand-400" size={22} /> Co-Lending Eligibility
            </h1>
            <p className="text-ink-muted text-sm mt-1">
              Credential reuse across lenders — co-lending eligibility resolved in seconds, not the 2-5 day manual reconciliation window.
            </p>
          </div>

          <div className="card p-6">
            <StepIndicator step={step} />

            {error && (
              <div className="flex items-center gap-2 p-3 mb-4 bg-surface-panelHover border border-hairline rounded-lg text-ink-secondary text-sm">
                <AlertTriangle size={15} className="text-ink-muted" /> {error}
              </div>
            )}

            {/* Step 1 */}
            {step === 1 && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-ink-primary font-medium">
                  <Building2 size={16} className="text-brand-400" /> Originating RE (Bank A) verifies the customer
                </div>
                <form onSubmit={handleVerify} className="flex gap-3 items-end">
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
                    {loading ? <><Loader2 size={14} className="animate-spin" /> Verifying…</> : <><Search size={14} /> Verify</>}
                  </button>
                </form>
              </div>
            )}

            {/* Step 2 */}
            {step === 2 && result && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-ink-primary font-medium">
                  <Building2 size={16} className="text-accent-verified" /> Partner RE (Co-Lending NBFC) reuses the same credential
                </div>
                <div className="bg-accent-verifiedDim border border-accent-verified rounded-lg p-3 text-xs text-accent-verified">
                  No re-verification required — the partner reads the VERITAS credential assertion issued in Step 1. Raw PII (PAN, Aadhaar, address) was never shared cross-lender; only the credential assertion is.
                </div>
                <CredentialCard
                  credential={result.did_credential}
                  kycStatus={result.kyc_status}
                  riskTier={result.risk_tier}
                  label="Reused Credential (Partner View)"
                />
                <div className="flex justify-between">
                  <button onClick={() => setStep(1)} className="btn-secondary text-sm">
                    <ArrowLeft size={14} /> Back
                  </button>
                  <button onClick={() => setStep(3)} className="btn-primary text-sm">
                    Continue <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* Step 3 */}
            {step === 3 && result && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-ink-primary font-medium">
                  <CheckCircle2 size={16} className="text-brand-400" /> Eligibility decision
                </div>
                <div className="flex items-center justify-between bg-surface-base border border-hairline rounded-lg p-4">
                  <div>
                    <p className="text-xs text-ink-muted mb-1">Outcome</p>
                    <Badge value={result.eligibility_outcome} size="lg" />
                  </div>
                  {result.eligibility_confidence != null && (
                    <div className="text-right">
                      <p className="text-xs text-ink-muted mb-1">Confidence</p>
                      <p className="text-sm font-semibold text-ink-primary font-mono">{(result.eligibility_confidence * 100).toFixed(0)}%</p>
                    </div>
                  )}
                </div>
                {result.eligibility_rule_id && (
                  <div>
                    <p className="text-xs text-ink-muted mb-1.5">Policy Citation</p>
                    <CitationChip ruleId={result.eligibility_rule_id} />
                  </div>
                )}
                <div className="flex justify-between">
                  <button onClick={() => setStep(2)} className="btn-secondary text-sm">
                    <ArrowLeft size={14} /> Back
                  </button>
                  <button onClick={reset} className="btn-secondary text-sm">
                    Run another customer
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  )
}
