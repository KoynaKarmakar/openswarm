import { ShieldCheck } from 'lucide-react'

export default function CredentialCard({ credential, kycStatus, riskTier, label = 'DID-Ready Credential' }) {
  if (!credential?.credentialSubject) return null

  return (
    <div className="p-3 bg-surface-base rounded-lg border border-hairline">
      <p className="text-xs font-semibold text-ink-muted mb-2 flex items-center gap-1">
        <ShieldCheck size={12} /> {label}
      </p>
      <div className="font-mono text-xs text-ink-muted space-y-0.5">
        <div>issuer: <span className="text-brand-400">{credential.issuer}</span></div>
        <div>kyc_status: <span className="text-accent-verified">{kycStatus ?? credential.credentialSubject.kyc_status}</span></div>
        <div>risk_tier: <span className="text-accent-flagged">{riskTier ?? credential.credentialSubject.risk_tier}</span></div>
        <div className="text-ink-muted italic text-xs mt-1">— no raw PII in credential —</div>
      </div>
    </div>
  )
}
