import { useState, useCallback } from 'react'
import { ClipboardList, RefreshCw, ShieldCheck, ShieldX, Link, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import Layout from '../components/Layout'
import Badge from '../components/Badge'
import CitationChip from '../components/CitationChip'
import { extractRuleIds } from '../data/citations'
import { getAuditTrail, verifyChain } from '../api/client'

function HashChip({ hash, truncate = true }) {
  if (!hash) return <span className="text-ink-muted text-xs">—</span>
  const display = truncate ? `${hash.slice(0, 8)}…${hash.slice(-8)}` : hash
  return (
    <span className="hash-mono text-xs bg-hairline px-2 py-0.5 rounded" title={hash}>
      {display}
    </span>
  )
}

function AuditRow({ record, index }) {
  const [open, setOpen] = useState(false)
  const ruleIds = extractRuleIds(record.trace)

  return (
    <div className="card border border-hairline overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-4 p-4 hover:bg-surface-base transition-colors text-left"
      >
        {/* Block number */}
        <div className="w-8 h-8 rounded-lg bg-hairline text-ink-primary flex items-center justify-center text-xs font-bold flex-shrink-0 font-mono">
          #{index + 1}
        </div>

        {/* Type — category label only, the Badge next to it carries the actual status semantics */}
        <span className="text-xs font-semibold px-2 py-0.5 rounded flex-shrink-0 bg-hairline text-ink-muted font-mono">
          {record.decision_type}
        </span>

        {/* Outcome */}
        <Badge value={record.outcome} />

        {/* Hash chain link icon */}
        <Link size={12} className="text-ink-muted flex-shrink-0" />

        {/* Hashes */}
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <span className="text-xs text-ink-muted">prev:</span>
          <HashChip hash={record.prev_hash} />
          <span className="text-xs text-ink-muted mx-1">→</span>
          <span className="text-xs text-ink-muted">curr:</span>
          <HashChip hash={record.curr_hash} />
        </div>

        {/* Timestamp */}
        <span className="text-xs text-ink-muted flex-shrink-0">
          {new Date(record.created_at).toLocaleTimeString()}
        </span>

        {open ? <ChevronDown size={14} className="text-ink-muted" /> : <ChevronRight size={14} className="text-ink-muted" />}
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-hairline pt-3 space-y-3">
          {/* Full hashes */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-ink-muted mb-1">Previous Hash</p>
              <p className="hash-mono text-xs break-all">{record.prev_hash ?? 'GENESIS'}</p>
            </div>
            <div>
              <p className="text-xs text-ink-muted mb-1">Current Hash</p>
              <p className="hash-mono text-xs break-all">{record.curr_hash}</p>
            </div>
          </div>

          {/* Confidence */}
          {record.confidence !== null && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-ink-muted">Confidence:</span>
              <span className="text-xs font-semibold text-ink-primary font-mono">{(record.confidence * 100).toFixed(0)}%</span>
            </div>
          )}

          {/* Citation — the rule(s) that actually fired for this decision */}
          {ruleIds.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-ink-muted">Policy Rule:</span>
              {ruleIds.map(r => <CitationChip key={r} ruleId={r} />)}
            </div>
          )}

          {/* Trace */}
          {record.trace?.length > 0 && (
            <div>
              <p className="text-xs text-ink-muted mb-2">Agent Trace</p>
              <div className="space-y-0.5 max-h-40 overflow-y-auto">
                {record.trace.map((step, i) => (
                  <div key={i} className="trace-step">{step}</div>
                ))}
              </div>
            </div>
          )}

          {/* Request ID */}
          <div>
            <p className="text-xs text-ink-muted">Request ID</p>
            <p className="hash-mono text-xs">{record.request_id}</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AuditTimeline() {
  const [records, setRecords]       = useState([])
  const [verifyResult, setVerify]   = useState(null)
  const [loadingFetch, setLoadingF] = useState(false)
  const [loadingVerify, setLoadingV]= useState(false)
  const [error, setError]           = useState('')
  const [limit, setLimit]           = useState(20)

  const fetchAudit = useCallback(async () => {
    setLoadingF(true); setError(''); setVerify(null)
    try {
      const data = await getAuditTrail(limit)
      setRecords(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load audit trail')
    } finally { setLoadingF(false) }
  }, [limit])

  async function handleVerify() {
    setLoadingV(true); setError('')
    try {
      const res = await verifyChain()
      setVerify(res)
    } catch (err) {
      setError(err.response?.data?.detail || 'Chain verification failed')
    } finally { setLoadingV(false) }
  }

  return (
    <Layout>
      <div className="px-8 py-6 flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-ink-primary flex items-center gap-2">
                <ClipboardList className="text-brand-400" size={22} /> Audit Timeline
              </h1>
              <p className="text-ink-muted text-sm mt-1">SHA-256 hash-chain — every decision linked · immutable ledger</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleVerify}
                disabled={loadingVerify || records.length === 0}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium border border-accent-verified/40 text-accent-verified hover:bg-accent-verified/10 rounded-lg transition-colors disabled:opacity-40"
              >
                {loadingVerify ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                Verify Integrity
              </button>
              <button
                onClick={fetchAudit}
                disabled={loadingFetch}
                className="btn-primary text-sm"
              >
                {loadingFetch ? <><Loader2 size={14} className="animate-spin" /> Loading…</> : <><RefreshCw size={14} /> Load Records</>}
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 mb-4 bg-surface-panelHover border border-hairline rounded-lg text-ink-secondary text-sm">
              {error}
            </div>
          )}

          {/* Integrity verification banner — legitimate critical use: a broken
              hash chain IS a tamper/fraud-adjacent event, not a generic error. */}
          {verifyResult && (
            <div className={`flex items-start gap-3 p-4 rounded-xl mb-5 border ${
              verifyResult.valid
                ? 'bg-accent-verifiedDim border-accent-verified text-accent-verified'
                : 'bg-accent-criticalDim border-accent-critical text-accent-critical'
            }`}>
              {verifyResult.valid
                ? <ShieldCheck size={18} className="flex-shrink-0 mt-0.5" />
                : <ShieldX size={18} className="flex-shrink-0 mt-0.5" />
              }
              <div>
                <p className="font-semibold text-sm">
                  {verifyResult.valid ? 'Chain Integrity Verified' : 'Chain Integrity Broken!'}
                </p>
                <p className="text-xs mt-0.5">
                  {verifyResult.valid
                    ? `All ${verifyResult.records_checked} records verified. SHA-256 chain is intact.`
                    : `Break detected at record #${verifyResult.break_at_index + 1}: ${verifyResult.break_reason}`
                  }
                </p>
              </div>
            </div>
          )}

          {/* Records */}
          {records.length === 0 && !loadingFetch && (
            <div className="text-center py-20 text-ink-muted">
              <ClipboardList size={40} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm mb-3">No records loaded yet.</p>
              <p className="text-xs">Click "Load Records" to fetch from the audit ledger.<br />
                Run some identity or fraud checks first to populate the chain.</p>
            </div>
          )}

          {loadingFetch && (
            <div className="flex items-center justify-center py-20 text-ink-muted">
              <Loader2 size={22} className="animate-spin mr-3" /> Loading audit records…
            </div>
          )}

          <div className="space-y-3">
            {records.map((rec, i) => (
              <AuditRow key={rec.id ?? i} record={rec} index={i} />
            ))}
          </div>

          {records.length > 0 && (
            <div className="mt-5 flex items-center justify-between text-xs text-ink-muted">
              <span>Showing {records.length} most recent records</span>
              {records.length === limit && (
                <button
                  onClick={() => setLimit(l => l + 20)}
                  className="text-brand-400 hover:underline"
                >
                  Load more
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
