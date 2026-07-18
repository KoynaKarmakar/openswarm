import { useState } from 'react'
import { ChevronDown, ChevronRight, HeartPulse } from 'lucide-react'

function tone(score) {
  if (score >= 85) return { text: 'text-accent-verified', bar: 'bg-accent-verified', chip: 'bg-accent-verifiedDim text-accent-verified' }
  if (score >= 60) return { text: 'text-accent-flagged', bar: 'bg-accent-flagged', chip: 'bg-accent-flaggedDim text-accent-flagged' }
  return { text: 'text-accent-critical', bar: 'bg-accent-critical', chip: 'bg-accent-criticalDim text-accent-critical' }
}

export default function HealthScorePanel({ healthScore }) {
  const [open, setOpen] = useState(false)
  if (!healthScore) return null

  const { overall, components } = healthScore
  const t = tone(overall)

  return (
    <div className="border border-hairline rounded-lg overflow-hidden mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full px-4 py-2.5 bg-surface-base hover:bg-surface-panelHover text-sm font-medium text-ink-primary transition-colors"
      >
        <span className="flex items-center gap-2">
          <HeartPulse size={14} className="text-brand-500" />
          Explainability Health Score
          <span className={`px-1.5 py-0.5 text-xs rounded font-semibold font-mono ${t.chip}`}>
            {overall}/100
          </span>
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {open && (
        <div className="px-4 py-3 bg-surface-panel space-y-3">
          <p className="text-xs text-ink-muted">
            Composite of every signal the fraud model has about how trustworthy this
            decision is — every underlying metric is broken out below.
          </p>
          {Object.entries(components).map(([key, c]) => {
            const ct = tone(c.score)
            return (
              <div key={key}>
                <div className="flex justify-between items-baseline mb-1">
                  <span className="text-xs font-semibold text-ink-muted">
                    {c.label} <span className="text-ink-muted font-normal">(weight {(c.weight * 100).toFixed(0)}%)</span>
                  </span>
                  <span className={`text-xs font-bold font-mono ${ct.text}`}>{c.score}/100</span>
                </div>
                <div className="h-1.5 bg-hairline rounded-full overflow-hidden">
                  <div className={`h-full ${ct.bar} rounded-full`} style={{ width: `${c.score}%` }} />
                </div>
                <p className="text-xs text-ink-muted mt-1">{c.description}</p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
