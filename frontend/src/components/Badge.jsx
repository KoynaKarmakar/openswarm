const OUTCOME_STYLES = {
  APPROVED:            'bg-accent-verifiedDim text-accent-verified border-accent-verified',
  APPROVED_FAST_TRACK: 'bg-accent-verifiedDim text-accent-verified border-accent-verified',
  APPROVED_STANDARD:   'bg-accent-verifiedDim text-accent-verified border-accent-verified',
  VERIFIED:            'bg-accent-verifiedDim text-accent-verified border-accent-verified',
  AUTO_RESOLVED:       'bg-accent-verifiedDim text-accent-verified border-accent-verified',
  REJECTED:            'bg-accent-criticalDim text-accent-critical border-accent-critical',
  EXPIRED:             'bg-accent-criticalDim text-accent-critical border-accent-critical',
  FLAGGED:             'bg-accent-flaggedDim text-accent-flagged border-accent-flagged',
  NEEDS_REVIEW:        'bg-accent-flaggedDim text-accent-flagged border-accent-flagged',
  UNDER_REVIEW:        'bg-accent-flaggedDim text-accent-flagged border-accent-flagged',
  ESCALATED:           'bg-accent-flaggedDim text-accent-flagged border-accent-flagged',
  PENDING:             'bg-accent-flaggedDim text-accent-flagged border-accent-flagged',
  OVERRIDDEN:          'bg-surface-panelHover text-ink-secondary border-hairline',
}

export default function Badge({ value, size = 'sm' }) {
  const style = OUTCOME_STYLES[value] ?? 'bg-surface-panelHover text-ink-secondary border-hairline'
  const sz = size === 'lg' ? 'px-3 py-1 text-sm font-semibold' : 'px-2 py-0.5 text-xs font-medium'
  return (
    <span className={`inline-block rounded-full border font-mono ${sz} ${style}`}>
      {value?.replace(/_/g, ' ')}
    </span>
  )
}
