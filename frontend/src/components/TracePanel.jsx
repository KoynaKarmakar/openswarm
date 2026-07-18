import { useState } from 'react'
import { ChevronDown, ChevronRight, Activity } from 'lucide-react'

export default function TracePanel({ trace = [], memoryHit = false, modelUsed = null }) {
  const [open, setOpen] = useState(false)
  if (!trace.length) return null

  return (
    <div className="border border-hairline rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full px-4 py-2.5 bg-surface-base hover:bg-surface-panelHover text-sm font-medium text-ink-primary transition-colors"
      >
        <span className="flex items-center gap-2">
          <Activity size={14} className="text-brand-500" />
          Explainability Trace
          <span className="text-xs text-ink-muted font-normal">({trace.length} steps)</span>
          {memoryHit && (
            <span className="px-1.5 py-0.5 text-xs bg-brand-500/15 text-brand-300 rounded font-medium font-mono">
              CACHE HIT
            </span>
          )}
          {modelUsed && (
            <span className="px-1.5 py-0.5 text-xs bg-hairline text-ink-muted rounded font-medium font-mono">
              {modelUsed.split('/').pop()}
            </span>
          )}
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {open && (
        <div className="px-4 py-3 bg-surface-panel space-y-0.5 max-h-64 overflow-y-auto">
          {trace.map((step, i) => (
            <div key={i} className="trace-step">{step}</div>
          ))}
        </div>
      )}
    </div>
  )
}
