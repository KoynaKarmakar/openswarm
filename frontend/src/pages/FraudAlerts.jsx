import { useState } from 'react'
import { ShieldAlert, Search, Loader2, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import Layout from '../components/Layout'
import Badge from '../components/Badge'
import TracePanel from '../components/TracePanel'
import HealthScorePanel from '../components/HealthScorePanel'
import CitationChip from '../components/CitationChip'
import { checkFraud } from '../api/client'

const DEMO_ACCOUNTS = ['ACC000010', 'ACC000020', 'ACC000030', 'ACC000040', 'ACC000050']

function ScoreGauge({ score }) {
  const pct = (score * 100).toFixed(1)
  const color = score > 0.85 ? 'text-accent-critical' : score > 0.60 ? 'text-accent-flagged' : 'text-accent-verified'
  const barColor = score > 0.85 ? 'bg-accent-critical' : score > 0.60 ? 'bg-accent-flagged' : 'bg-accent-verified'
  const label = score > 0.85 ? 'HIGH RISK' : score > 0.60 ? 'MEDIUM' : 'LOW RISK'

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center">
        <span className={`text-2xl font-bold font-mono ${color}`}>{pct}%</span>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
          score > 0.85 ? 'bg-accent-criticalDim text-accent-critical' :
          score > 0.60 ? 'bg-accent-flaggedDim text-accent-flagged' :
          'bg-accent-verifiedDim text-accent-verified'
        }`}>{label}</span>
      </div>
      <div className="h-3 bg-hairline rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between text-xs text-ink-muted">
        <span>0%</span><span>60%</span><span>85%</span><span>100%</span>
      </div>
    </div>
  )
}

function ResultCard({ result }) {
  const severe = result.outcome === 'REJECTED'
  const attention = result.outcome === 'FLAGGED' || result.outcome === 'NEEDS_REVIEW'

  return (
    <div className={`card p-5 border-l-4 ${
      severe ? 'border-l-accent-critical' :
      attention ? 'border-l-accent-flagged' :
      'border-l-accent-verified'
    }`}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            {severe
              ? <XCircle size={16} className="text-accent-critical" />
              : attention
              ? <AlertTriangle size={16} className="text-accent-flagged" />
              : <CheckCircle2 size={16} className="text-accent-verified" />
            }
            <span className="font-semibold text-ink-primary text-sm font-mono">{result.account_id}</span>
          </div>
          <p className="text-xs text-ink-muted mt-0.5">{result.transactions_checked} transactions analysed</p>
        </div>
        <div className="flex items-center gap-2">
          {result.health_score && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-hairline text-ink-muted font-mono" title="Explainability Health Score">
              Health {result.health_score.overall}/100
            </span>
          )}
          <Badge value={result.outcome} size="lg" />
        </div>
      </div>

      {result.fraud_score !== null && (
        <div className="mb-4">
          <ScoreGauge score={result.fraud_score} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 mb-4">
        {result.rule_id && (
          <div className="bg-surface-base rounded-lg p-3">
            <p className="text-xs text-ink-muted mb-1.5">Policy Rule</p>
            <CitationChip ruleId={result.rule_id} />
          </div>
        )}
        <div className="bg-surface-base rounded-lg p-3">
          <p className="text-xs text-ink-muted mb-0.5">Confidence</p>
          <p className="text-sm font-semibold text-ink-primary font-mono">{(result.confidence * 100).toFixed(0)}%</p>
        </div>
      </div>

      <HealthScorePanel healthScore={result.health_score} />
      <TracePanel trace={result.trace} />
    </div>
  )
}

export default function FraudAlerts() {
  const [accountId, setAccountId] = useState('CUST000010')
  const [results, setResults]     = useState([])
  const [loading, setLoading]     = useState(false)
  const [batchLoading, setBatchLoading] = useState(false)
  const [error, setError]         = useState('')

  async function handleSingle(e) {
    e.preventDefault()
    if (!accountId.trim()) return
    setLoading(true); setError('')
    try {
      const res = await checkFraud(accountId.trim())
      setResults(prev => [{ ...res, account_id: accountId.trim() }, ...prev.filter(r => r.account_id !== accountId.trim())])
    } catch (err) {
      setError(err.response?.data?.detail || 'Fraud check failed')
    } finally { setLoading(false) }
  }

  async function handleBatch() {
    setBatchLoading(true); setError('')
    const newResults = []
    for (const id of DEMO_ACCOUNTS) {
      try {
        const res = await checkFraud(id)
        newResults.push({ ...res, account_id: id })
      } catch {
        // skip failed
      }
    }
    setResults(prev => {
      const existing = prev.filter(r => !DEMO_ACCOUNTS.includes(r.account_id))
      return [...newResults, ...existing]
    })
    setBatchLoading(false)
  }

  const blocked = results.filter(r => r.outcome === 'REJECTED')
  const review  = results.filter(r => r.outcome === 'FLAGGED' || r.outcome === 'NEEDS_REVIEW')
  const clear   = results.filter(r => r.outcome !== 'REJECTED' && r.outcome !== 'FLAGGED' && r.outcome !== 'NEEDS_REVIEW')

  return (
    <Layout>
      <div className="px-8 py-6 flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-ink-primary flex items-center gap-2">
                <ShieldAlert className="text-brand-400" size={22} /> Fraud Alerts
              </h1>
              <p className="text-ink-muted text-sm mt-1">XGBoost model · UEBT policy rules · all checks audit-logged</p>
            </div>
            <button
              onClick={handleBatch}
              disabled={batchLoading || loading}
              className="btn-primary text-sm"
            >
              {batchLoading ? <><Loader2 size={14} className="animate-spin" /> Running batch…</> : 'Run Demo Batch (5 accounts)'}
            </button>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 mb-4 bg-surface-panelHover border border-hairline rounded-lg text-ink-secondary text-sm">
              <AlertTriangle size={15} className="text-ink-muted" /> {error}
            </div>
          )}

          {/* Single check */}
          <div className="card p-4 mb-6">
            <form onSubmit={handleSingle} className="flex gap-3 items-end">
              <div className="flex-1">
                <label className="label">Account ID</label>
                <input
                  className="input"
                  value={accountId}
                  onChange={e => setAccountId(e.target.value)}
                  placeholder="CUST000010"
                />
              </div>
              <button type="submit" className="btn-primary" disabled={loading || batchLoading}>
                {loading ? <><Loader2 size={14} className="animate-spin" /> Checking…</> : <><Search size={14} /> Check Account</>}
              </button>
            </form>
          </div>

          {/* Summary cards */}
          {results.length > 0 && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="card p-4 border-t-4 border-t-accent-critical">
                <p className="text-3xl font-bold text-accent-critical font-mono">{blocked.length}</p>
                <p className="text-sm text-ink-muted mt-1">Blocked / Rejected</p>
              </div>
              <div className="card p-4 border-t-4 border-t-accent-flagged">
                <p className="text-3xl font-bold text-accent-flagged font-mono">{review.length}</p>
                <p className="text-sm text-ink-muted mt-1">Needs Review</p>
              </div>
              <div className="card p-4 border-t-4 border-t-accent-verified">
                <p className="text-3xl font-bold text-accent-verified font-mono">{clear.length}</p>
                <p className="text-sm text-ink-muted mt-1">Clear</p>
              </div>
            </div>
          )}

          {/* Results */}
          {results.length === 0 && !loading && !batchLoading && (
            <div className="text-center py-20 text-ink-muted">
              <ShieldAlert size={40} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">No results yet. Enter an account ID or run the demo batch above.</p>
            </div>
          )}

          <div className="space-y-4">
            {[...blocked, ...review, ...clear].map(r => (
              <ResultCard key={r.account_id} result={r} />
            ))}
          </div>
        </div>
      </div>
    </Layout>
  )
}
