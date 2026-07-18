import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X, ScrollText, Loader2, AlertTriangle } from 'lucide-react'
import { getCitation } from '../data/citations'
import { getPolicyCitation } from '../api/client'

// Reusable body — used both inside the overlay drawer (other pages) and
// inline in Case Queue's Audit/Citation pane. Fetches the REAL clause from
// the Qdrant RAG layer; falls back to the static citations.js entry (still
// labeled as such) if the live call fails or Qdrant is unavailable.
export function CitationContent({ ruleId }) {
  const fallback = getCitation(ruleId)
  const [state, setState] = useState({ loading: true, live: null, error: false })

  useEffect(() => {
    let cancelled = false
    setState({ loading: true, live: null, error: false })
    getPolicyCitation(ruleId)
      .then(data => { if (!cancelled) setState({ loading: false, live: data, error: false }) })
      .catch(() => { if (!cancelled) setState({ loading: false, live: null, error: true }) })
    return () => { cancelled = true }
  }, [ruleId])

  const live = state.live && state.live.source === 'qdrant' ? state.live : null
  const doc = live?.policy_name || fallback?.doc
  const section = live?.section || fallback?.section
  const ref = live?.ref || fallback?.ref
  const refLabel = live?.ref_label || fallback?.refLabel
  const text = live?.text || fallback?.text

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs text-ink-muted mb-1">Clause</p>
        <p className="font-mono text-sm text-ink-secondary">{section || '—'}</p>
      </div>

      <div>
        <p className="text-xs text-ink-muted mb-1">External Reference</p>
        <p className="font-mono text-sm text-ink-primary">{ref || '—'}</p>
        <p className="text-xs text-ink-muted mt-0.5">{refLabel}</p>
      </div>

      <div>
        <p className="text-xs text-ink-muted mb-1.5 flex items-center gap-1.5">
          <ScrollText size={12} /> Rule Text — this is the rule that fired
        </p>
        {state.loading ? (
          <div className="flex items-center gap-2 text-xs text-ink-muted bg-surface-base border border-hairline rounded-lg p-3">
            <Loader2 size={13} className="animate-spin" /> Retrieving clause from Qdrant…
          </div>
        ) : (
          <p className="text-sm text-ink-primary leading-relaxed bg-surface-base border border-hairline rounded-lg p-3">
            {text || 'No clause text available.'}
          </p>
        )}
        {!state.loading && (
          <p className="text-xs text-ink-muted mt-1.5 flex items-center gap-1">
            {live ? (
              <>retrieved live from Qdrant{live.score != null && ` · relevance ${live.score}`}</>
            ) : (
              <><AlertTriangle size={11} className="text-accent-flagged" /> live retrieval unavailable — showing cached reference text</>
            )}
          </p>
        )}
      </div>

      {doc && <p className="text-xs text-ink-muted">Source document: {doc}</p>}
    </div>
  )
}

function CitationDrawer({ ruleId, onClose }) {
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-md h-full bg-surface-panel border-l border-hairline flex flex-col shadow-xl">
        <div className="flex items-start justify-between px-5 py-4 border-b border-hairline">
          <p className="text-xs text-ink-muted font-mono">{ruleId}</p>
          <button onClick={onClose} className="text-ink-muted hover:text-ink-primary p-1 -mr-1">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <CitationContent ruleId={ruleId} />
        </div>
      </div>
    </div>,
    document.body
  )
}

export default function CitationChip({ ruleId }) {
  const [open, setOpen] = useState(false)
  const citation = getCitation(ruleId)

  if (!ruleId) return null

  // Even without a known citation mapping, still show the rule id in mono —
  // the point is nothing is ever hidden, just not always cross-referenced yet.
  // Citations are content, not state — neutral mono chip, never colored.
  if (!citation) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded border border-hairline bg-surface-panel text-ink-secondary text-xs font-mono">
        {ruleId}
      </span>
    )
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-hairline bg-surface-panel text-ink-secondary text-xs font-mono hover:bg-surface-panelHover hover:border-brand-500/40 transition-colors"
        title="Click to view clause text and source rule"
      >
        {citation.doc.replace(/ Policy$/, '')} {citation.section} → {citation.ref}
      </button>
      {open && <CitationDrawer ruleId={ruleId} onClose={() => setOpen(false)} />}
    </>
  )
}
