import { useEffect, useState } from 'react'
import { Loader2, ShieldCheck, ShieldX, Link as LinkIcon } from 'lucide-react'
import { getAuditRecordByDecision } from '../api/client'

export default function HashChainEntry({ decisionId }) {
  const [state, setState] = useState({ loading: true, record: null })

  useEffect(() => {
    if (!decisionId) { setState({ loading: false, record: null }); return }
    let cancelled = false
    setState({ loading: true, record: null })
    getAuditRecordByDecision(decisionId)
      .then(data => { if (!cancelled) setState({ loading: false, record: data }) })
      .catch(() => { if (!cancelled) setState({ loading: false, record: null }) })
    return () => { cancelled = true }
  }, [decisionId])

  if (!decisionId) {
    return <p className="text-xs text-ink-muted">No decision linked to this case yet.</p>
  }

  if (state.loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-ink-muted">
        <Loader2 size={13} className="animate-spin" /> Looking up hash-chain entry…
      </div>
    )
  }

  const record = state.record
  if (!record || !record.found) {
    return (
      <p className="text-xs text-ink-muted">
        {record?.note || 'Not yet written to the ledger — outbox worker flushes every few seconds. Reload to check again.'}
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <div className={`flex items-center gap-2 text-xs font-semibold ${record.hash_valid ? 'text-accent-verified' : 'text-accent-critical'}`}>
        {record.hash_valid ? <ShieldCheck size={14} /> : <ShieldX size={14} />}
        {record.hash_valid ? 'Hash verified — entry is tamper-evident intact' : 'Hash mismatch — entry integrity broken'}
      </div>

      <div className="flex items-center gap-1.5 min-w-0">
        <LinkIcon size={11} className="text-ink-muted flex-shrink-0" />
        <span className="text-xs text-ink-muted">prev:</span>
        <span className="hash-mono text-xs bg-hairline px-1.5 py-0.5 rounded truncate" title={record.prev_hash}>
          {record.prev_hash ? `${record.prev_hash.slice(0, 10)}…` : 'GENESIS'}
        </span>
      </div>
      <div className="flex items-center gap-1.5 min-w-0">
        <LinkIcon size={11} className="text-ink-muted flex-shrink-0" />
        <span className="text-xs text-ink-muted">curr:</span>
        <span className="hash-mono text-xs bg-hairline px-1.5 py-0.5 rounded truncate" title={record.curr_hash}>
          {record.curr_hash?.slice(0, 10)}…
        </span>
      </div>

      <div>
        <p className="text-xs text-ink-muted mb-1">Ledger Timestamp</p>
        <p className="text-xs text-ink-primary font-mono">{new Date(record.created_at).toLocaleString()}</p>
      </div>
    </div>
  )
}
