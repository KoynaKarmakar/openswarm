import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, AlertCircle } from 'lucide-react'
import { login } from '../api/client'

const DEMO_CREDS = { email: 'demo@idbi.bank', password: 'demo1234' }

export default function Login() {
  const [email, setEmail]     = useState(DEMO_CREDS.email)
  const [password, setPassword] = useState(DEMO_CREDS.password)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface-base flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-white/10 rounded-2xl mb-4">
            <Shield className="text-accent-verified" size={28} />
          </div>
          <h1 className="text-2xl font-display font-bold text-ink-primary">VERITAS Fabric</h1>
          <p className="text-ink-muted text-sm mt-1">AI Trust Middleware for Banking</p>
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-display font-semibold text-ink-primary mb-5">Sign in</h2>

          {error && (
            <div className="flex items-center gap-2 p-3 mb-4 bg-surface-panelHover border border-hairline rounded-lg text-ink-secondary text-sm">
              <AlertCircle size={15} className="flex-shrink-0 text-ink-muted" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">Email</label>
              <input
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={loading}>
              {loading ? 'Authenticating…' : 'Sign in'}
            </button>
          </form>

          <p className="text-xs text-ink-muted text-center mt-4">
            Demo account pre-filled above
          </p>
        </div>

        <p className="text-xs text-ink-muted text-center mt-6 font-mono">
          Prototype using synthetic data · IDBI Innovate 2026
        </p>
      </div>
    </div>
  )
}
