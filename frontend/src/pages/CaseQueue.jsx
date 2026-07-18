import { useState, useEffect, useCallback } from 'react'
import { Inbox, Loader2, AlertTriangle, RefreshCw, Check, X, ScrollText } from 'lucide-react'
import Layout from '../components/Layout'
import Badge from '../components/Badge'
import SlaCountdown from '../components/SlaCountdown'
import HashChainEntry from '../components/HashChainEntry'
import CitationChip, { CitationContent } from '../components/CitationChip'
import { getCitation } from '../data/citations'
import { getCases, getCase, overrideCase } from '../api/client'

function CaseRow({ c, active, onSelect }) {
  return (
    <button
      onClick={() => onSelect(c.id)}
      className={`w-full text-left px-3 py-2.5 rounded-lg border transition-colors ${
        active ? 'bg-brand-500/10 border-brand-500/40' : 'bg-surface-panel border-hairline hover:border-brand-500/30'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-sm text-ink-primary">{c.account_id}</span>
        <Badge value={c.status} />
      </div>
      <div className="flex items-center justify-between text-xs text-ink-muted">
        <span>{c.liability_tier.replace(/_/g, ' ')}</span>
        <SlaCountdown deadline={c.sla_deadline} />
      </div>
    </button>
  )
}

function ScoreBar({ score }) {
  const pct = (score * 100).toFixed(1)
  const textColor = score > 0.85 ? 'text-accent-critical' : score > 0.60 ? 'text-accent-flagged' : 'text-accent-verified'
  const barColor = score > 0.85 ? 'bg-accent-critical' : score > 0.60 ? 'bg-accent-flagged' : 'bg-accent-verified'
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <span className={`text-xl font-bold font-mono ${textColor}`}>{pct}%</span>
        <span className="text-xs text-ink-muted">fraud score</span>
      </div>
      <div className="h-2 bg-hairline rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function OverrideControl({ caseId, onDone }) {
  const [action, setAction] = useState(null) // 'ACCEPT' | 'REJECT'
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    if (!reason.trim()) { setError('A reason is required for an override.'); return }
    setSubmitting(true); setError('')
    try {
      await overrideCase(caseId, action, reason.trim())
      setAction(null); setReason('')
      onDone()
    } catch (err) {
      setError(err.response?.data?.detail || 'Override failed')
    } finally { setSubmitting(false) }
  }

  return (
    <div className="border border-hairline rounded-lg p-3 space-y-2.5">
      <p className="text-xs font-semibold text-ink-muted flex items-center gap-1.5">
        <ScrollText size={12} /> Human Override
      </p>
      <p className="text-xs text-ink-muted">
        A compliance officer can accept or reject the automated decision on this case. Every override is written to the audit ledger.
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => setAction('ACCEPT')}
          className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            action === 'ACCEPT' ? 'bg-accent-verifiedDim border-accent-verified text-accent-verified' : 'border-hairline text-ink-muted hover:border-accent-verified/40'
          }`}
        >
          <Check size={13} /> Accept
        </button>
        <button
          onClick={() => setAction('REJECT')}
          className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            action === 'REJECT' ? 'bg-accent-criticalDim border-accent-critical text-accent-critical' : 'border-hairline text-ink-muted hover:border-accent-critical/40'
          }`}
        >
          <X size={13} /> Reject
        </button>
      </div>
      {action && (
        <div className="space-y-2">
          <textarea
            className="input text-xs resize-none"
            rows={2}
            placeholder="Reason for this override (required, logged to audit trail)…"
            value={reason}
            onChange={e => setReason(e.target.value)}
          />
          {error && <p className="text-xs text-ink-secondary flex items-center gap-1"><AlertTriangle size={11} className="text-ink-muted" /> {error}</p>}
          <button onClick={submit} disabled={submitting} className="btn-primary text-xs w-full justify-center py-1.5">
            {submitting ? <><Loader2 size={12} className="animate-spin" /> Submitting…</> : `Confirm ${action.toLowerCase()}`}
          </button>
        </div>
      )}
    </div>
  )
}

export default function CaseQueue() {
  const [cases, setCases] = useState([])
  const [loadingList, setLoadingList] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState('')

  const fetchList = useCallback(async () => {
    setLoadingList(true); setError('')
    try {
      const data = await getCases()
      setCases(data)
      if (!selectedId && data.length > 0) setSelectedId(data[0].id)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load case queue')
    } finally { setLoadingList(false) }
  }, [selectedId])

  useEffect(() => { fetchList() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    let cancelled = false
    setLoadingDetail(true)
    getCase(selectedId)
      .then(data => { if (!cancelled) setDetail(data) })
      .catch(() => { if (!cancelled) setDetail(null) })
      .finally(() => { if (!cancelled) setLoadingDetail(false) })
    return () => { cancelled = true }
  }, [selectedId])

  async function handleOverrideDone() {
    await fetchList()
    const data = await getCase(selectedId)
    setDetail(data)
  }

  const citation = detail?.rule_id ? getCitation(detail.rule_id) : null

  return (
    <Layout>
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-hairline bg-surface-panel flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-lg font-display font-bold text-ink-primary flex items-center gap-2">
              <Inbox className="text-brand-400" size={19} /> Case Queue
            </h1>
            <p className="text-xs text-ink-muted mt-0.5">Cases open automatically when a fraud check resolves FLAGGED or NEEDS_REVIEW</p>
          </div>
          <button onClick={fetchList} disabled={loadingList} className="btn-secondary text-xs">
            {loadingList ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
          </button>
        </div>

        {error && (
          <div className="px-6 py-2 bg-surface-panelHover border-b border-hairline text-ink-secondary text-xs flex items-center gap-2 flex-shrink-0">
            <AlertTriangle size={12} className="text-ink-muted" /> {error}
          </div>
        )}

        <div className="flex-1 flex overflow-hidden">
          {/* Left: Case Queue */}
          <div className="w-72 border-r border-hairline overflow-y-auto p-3 space-y-2 flex-shrink-0">
            {cases.length === 0 && !loadingList && (
              <p className="text-xs text-ink-muted text-center py-10">
                No open cases. Run a fraud check batch (Fraud Alerts page) to populate the queue.
              </p>
            )}
            {cases.map(c => (
              <CaseRow key={c.id} c={c} active={c.id === selectedId} onSelect={setSelectedId} />
            ))}
          </div>

          {/* Center: Decision Detail */}
          <div className="flex-1 overflow-y-auto p-5">
            {loadingDetail && (
              <div className="flex items-center justify-center py-20 text-ink-muted">
                <Loader2 size={20} className="animate-spin mr-2" /> Loading case…
              </div>
            )}
            {!loadingDetail && !detail && (
              <div className="text-center py-20 text-ink-muted text-sm">Select a case from the queue.</div>
            )}
            {!loadingDetail && detail && (
              <div className="max-w-lg space-y-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-display font-semibold text-ink-primary text-base font-mono">{detail.account_id}</h2>
                    <p className="text-xs text-ink-muted mt-0.5">customer: {detail.customer_id || 'unknown'}</p>
                  </div>
                  <Badge value={detail.status} size="lg" />
                </div>

                {detail.fraud_score != null && <ScoreBar score={detail.fraud_score} />}

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-surface-panel border border-hairline rounded-lg p-3">
                    <p className="text-xs text-ink-muted mb-0.5">Liability Tier</p>
                    <p className="text-sm font-semibold text-ink-primary font-mono">{detail.liability_tier.replace(/_/g, ' ')}</p>
                  </div>
                  <div className="bg-surface-panel border border-hairline rounded-lg p-3">
                    <p className="text-xs text-ink-muted mb-0.5">Compensation</p>
                    <p className="text-sm font-semibold text-ink-primary font-mono">{detail.compensation_percent}%</p>
                  </div>
                  <div className="bg-surface-panel border border-hairline rounded-lg p-3 col-span-2">
                    <p className="text-xs text-ink-muted mb-0.5">SLA Deadline</p>
                    <SlaCountdown deadline={detail.sla_deadline} />
                  </div>
                </div>

                {detail.rule_id && (
                  <div>
                    <p className="text-xs text-ink-muted mb-1.5">Rule Fired</p>
                    <CitationChip ruleId={detail.rule_id} />
                  </div>
                )}

                {detail.status !== 'OVERRIDDEN' && (
                  <OverrideControl caseId={detail.id} onDone={handleOverrideDone} />
                )}
              </div>
            )}
          </div>

          {/* Right: Audit / Citation */}
          <div className="w-80 border-l border-hairline overflow-y-auto p-4 flex-shrink-0 space-y-5">
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-2">Policy Citation</p>
              {detail?.rule_id ? (
                <CitationContent ruleId={detail.rule_id} />
              ) : (
                <p className="text-xs text-ink-muted">No rule fired for this case — select a case with a fired rule.</p>
              )}
            </div>
            {citation && <div className="border-t border-hairline pt-4" />}
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-2">Hash-Chain Entry</p>
              <HashChainEntry decisionId={detail?.decision_id} />
            </div>
          </div>
        </div>
      </div>
    </Layout>
  )
}
