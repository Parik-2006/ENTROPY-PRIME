/**
 * AppShell — authenticated layout for the Entropy Bank product surface.
 * Sidebar (brand + session trust + navigation + user) · Topbar (title + live
 * Identity Confidence widget + theme toggle) · routed page via <Outlet/> with
 * Framer Motion transitions.
 *
 * Global security UX lives here: the live confidence widget, the yellow
 * deviation banner, and the orange/red verification/block modal — all driven by
 * TrustContext (which derives from the real PHASE 4 watchdog + a demo trigger).
 */

import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { ThemeToggle } from './ui'
import IdentityConfidence from './IdentityConfidence'
import { TrustBanner, TrustModal } from './TrustGuards'
import s from './AppShell.module.css'

const NAV = [
  { section: 'Banking' },
  { to: '/app/dashboard',     label: 'Dashboard',      icon: '◧' },
  { to: '/app/ai',            label: 'AI Banker',      icon: '🤖' },
  { to: '/app/accounts',      label: 'Accounts',       icon: '▦' },
  { to: '/app/transfers',     label: 'Transfers',      icon: '⇄' },
  { to: '/app/beneficiaries', label: 'Beneficiaries',  icon: '☆' },
  { to: '/app/journal',       label: 'Money Journal',  icon: '📓' },
  { to: '/app/support',       label: 'Support Center', icon: '✉' },
  { to: '/app/profile',       label: 'Profile',        icon: '◉' },
  { section: 'Entropy Prime' },
  { to: '/app/security',      label: 'Security Center',     icon: '🛡' },
  { to: '/app/threats',       label: 'Threat Intelligence', icon: '◬' },
  { to: '/app/settings',      label: 'Settings',       icon: '⚙' },
]

const TITLES = {
  '/app/dashboard':     ['Dashboard', 'Your accounts at a glance'],
  '/app/ai':            ['AI Financial Assistant', 'Ask anything about your money'],
  '/app/accounts':      ['Accounts', 'Balances, notes and planning'],
  '/app/transfers':     ['Transfers', 'Send money securely'],
  '/app/beneficiaries': ['Beneficiaries', 'Manage your payees'],
  '/app/journal':       ['Money Journal', 'Daily financial reflection'],
  '/app/support':       ['Support Center', 'We are here to help'],
  '/app/profile':       ['Profile', 'Your personal details'],
  '/app/security':      ['Security Center', 'Entropy Prime — continuous identity assurance'],
  '/app/threats':       ['Threat Intelligence', 'Live threat feed & deception analytics'],
  '/app/settings':      ['Settings', 'Preferences & advanced'],
}

const trustColor = (t) => (t > 0.7 ? 'var(--accent)' : t > 0.4 ? 'var(--gold)' : 'var(--danger)')

export default function AppShell() {
  const { user, logout, trustScore } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [title, sub] = TITLES[location.pathname] || ['Entropy Bank', 'Protected by Entropy Prime']
  const tColor = trustColor(trustScore)

  return (
    <div className={s.shell}>
      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside className={s.sidebar}>
        <div className={s.brand}>
          <div className={s.logoMark}>EB</div>
          <div>
            <div className={s.brandName}>ENTROPY BANK</div>
            <div className={s.brandSub}>Protected by Entropy Prime</div>
          </div>
        </div>

        <div className={s.trust}>
          <div className={s.trustHead}>
            <span className={s.trustLabel}>Session Trust</span>
            <span className={s.trustVal} style={{ color: tColor }}>{(trustScore * 100).toFixed(0)}%</span>
          </div>
          <div style={{ height: 8, background: 'var(--surface-3)', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ width: `${trustScore * 100}%`, height: '100%', background: tColor, borderRadius: 999, transition: 'width .4s var(--ease)' }} />
          </div>
        </div>

        <nav className={s.nav}>
          {NAV.map((item, i) =>
            item.section ? (
              <div key={`sec-${i}`} className={s.navSection}>{item.section}</div>
            ) : (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => `${s.navItem} ${isActive ? s.navActive : ''}`}>
                <span className={s.navIcon}>{item.icon}</span>
                {item.label}
              </NavLink>
            ),
          )}
        </nav>

        <div className={s.userChip}>
          <div className={s.avatar}>{user?.email?.[0]?.toUpperCase() ?? 'U'}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className={s.userEmail}>{user?.email ?? 'guest'}</div>
            <div className={s.userId}>{(user?.id ?? '').toString().slice(0, 12)}</div>
          </div>
          <button className={s.logoutBtn} onClick={logout}>Exit</button>
        </div>
      </aside>

      {/* ── Main ─────────────────────────────────────────────────────────── */}
      <div className={s.main}>
        <header className={s.topbar}>
          <div>
            <div className={s.pageTitle}>{title}</div>
            <div className={s.pageSub}>{sub}</div>
          </div>
          <div className={s.topRight}>
            <IdentityConfidence />
            <ThemeToggle />
          </div>
        </header>

        <TrustBanner />

        <main className={s.content}>
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, ease: [0.4, 0, 0.2, 1] }}
          >
            <Outlet />
          </motion.div>
          <div className={s.protectedFoot}>
            🔒 This session is continuously protected by <b>Entropy Prime</b> behavioral security.
          </div>
        </main>
      </div>

      <TrustModal />
    </div>
  )
}
