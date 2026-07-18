import { NavLink, useNavigate } from 'react-router-dom'
import { clearToken } from '../api/client'
import {
  LayoutDashboard, MessageSquare, ShieldAlert,
  ClipboardList, Shield, LogOut, Inbox, Handshake, BadgeCheck, Network,
} from 'lucide-react'

const NAV = [
  { to: '/dashboard', label: 'Dashboard',      Icon: LayoutDashboard },
  { to: '/swarm',      label: 'Swarm Console', Icon: Network         },
  { to: '/assistant',  label: 'AI Assistant',  Icon: MessageSquare   },
  { to: '/fraud',      label: 'Fraud Alerts',  Icon: ShieldAlert     },
  { to: '/cases',      label: 'Case Queue',    Icon: Inbox           },
  { to: '/clm',        label: 'Co-Lending Eligibility', Icon: Handshake },
  { to: '/identity',   label: 'Identity / Credential',  Icon: BadgeCheck },
  { to: '/audit',      label: 'Audit Trail',   Icon: ClipboardList   },
]

export default function Layout({ children }) {
  const navigate = useNavigate()

  function handleLogout() {
    clearToken()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-60 bg-surface-panel border-r border-hairline flex flex-col flex-shrink-0">
        <div className="px-5 py-5 border-b border-hairline">
          <div className="flex items-center gap-2">
            <Shield className="text-accent-verified" size={22} />
            <div>
              <p className="text-ink-primary font-display font-bold text-sm leading-none">VERITAS</p>
              <p className="text-ink-muted text-xs mt-0.5">AI Trust Fabric</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-600/20 text-ink-primary border-l-2 border-brand-500'
                    : 'text-ink-muted hover:bg-surface-panelHover hover:text-ink-primary'
                }`
              }
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-hairline">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-3 py-2.5 text-ink-muted hover:text-ink-primary text-sm font-medium rounded-lg hover:bg-surface-panelHover transition-colors"
          >
            <LogOut size={17} />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-h-screen overflow-hidden">
        {children}
      </main>
    </div>
  )
}
