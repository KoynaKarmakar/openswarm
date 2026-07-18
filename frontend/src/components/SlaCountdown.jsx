import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'

function format(remainingMs) {
  const overdue = remainingMs < 0
  const abs = Math.abs(remainingMs)
  const totalSeconds = Math.floor(abs / 1000)
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const parts = days > 0 ? `${days}d ${hours}h ${minutes}m` : `${hours}h ${minutes}m ${seconds}s`
  return overdue ? `${parts} overdue` : parts
}

export default function SlaCountdown({ deadline }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  if (!deadline) return null

  const deadlineMs = new Date(deadline).getTime()
  const remaining = deadlineMs - now
  const overdue = remaining < 0
  const urgent = !overdue && remaining < 1000 * 60 * 60 * 6 // < 6h left

  const color = overdue ? 'text-accent-critical' : urgent ? 'text-accent-flagged' : 'text-accent-verified'

  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-sm font-semibold ${color}`}>
      <Clock size={13} /> {format(remaining)}
    </span>
  )
}
