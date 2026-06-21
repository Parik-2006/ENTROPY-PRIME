/**
 * Settings — appearance + the "Legacy / Advanced" gateway.
 * Per the rearchitecture constraint, no existing functionality is removed: the
 * original Entropy Prime screens remain fully reachable from here.
 */

import { useNavigate } from 'react-router-dom'
import { Card, ThemeToggle, Badge, Button } from '../../components/ui'
import { useTheme } from '../../context/ThemeContext'
import { useTrust } from '../../context/TrustContext'
import s from './bank.module.css'

const LEGACY = [
  { to: '/profile-build', icon: '◈', name: 'Profile Build (classic)', desc: 'Original biometric profile builder' },
  { to: '/dashboard',     icon: '◉', name: 'Biometric Dashboard (classic)', desc: 'Original live metrics view' },
  { to: '/threats',       icon: '◬', name: 'Threat Intel (classic)', desc: 'Original honeypot signatures table' },
  { to: '/admin',         icon: '🛠', name: 'Admin Dashboard', desc: 'Model status & pipeline diagnostics' },
  { to: '/sites',         icon: '🌐', name: 'Site Management', desc: 'Multi-tenant SaaS controls' },
]

export default function Settings() {
  const { theme } = useTheme()
  const { confidence, color, label, simulateSlowTypist, simulateFastTypist, simulateDifferentUser, simulateAttacker, resetTrust } = useTrust()
  const navigate = useNavigate()

  return (
    <div className={s.grid}>
      <Card title="Demo & Security Simulation" sub="Reliably trigger the trust-collapse demo for judges">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Current Identity Confidence</div>
            <div style={{ fontFamily: 'var(--display)', fontSize: 30, fontWeight: 800, color }}>{confidence}% <span style={{ fontSize: 14, fontWeight: 600 }}>· {label}</span></div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Button variant="subtle" onClick={simulateSlowTypist}>🐢 Simulate slow typist</Button>
            <Button variant="subtle" onClick={simulateFastTypist}>⚡ Simulate fast typist</Button>
            <Button variant="subtle" onClick={simulateDifferentUser}>🧑‍🤝‍🧑 Simulate different user</Button>
            <Button variant="danger" onClick={simulateAttacker}>🤖 Simulate attacker / bot</Button>
            <Button variant="ghost" onClick={resetTrust}>↺ Reset to verified</Button>
          </div>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 14, lineHeight: 1.6 }}>
          “Different user” drives confidence into the <strong>orange</strong> zone → a quick verification modal appears (same device, same session, correct password — but a different human). “Attacker / bot” drives it <strong>red</strong> → sensitive actions are blocked and re-authentication is required. Real biometric drift triggers the same flow automatically.
        </div>
      </Card>

      <Card title="Appearance" sub="Choose how Entropy Bank looks">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>Theme</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Currently using <strong>{theme}</strong> mode · saved to this device</div>
          </div>
          <ThemeToggle />
        </div>
      </Card>

      <Card title="Security Preferences" sub="Entropy Prime protections">
        {[
          ['Continuous authentication', 'Re-verify identity every 30s', true],
          ['Trust-gated transfers', 'Block sensitive actions on low trust', true],
          ['Generative honeypots', 'Shadow-route detected bots', true],
        ].map(([t, d, on]) => (
          <div key={t} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
            <div>
              <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{t}</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{d}</div>
            </div>
            <Badge tone={on ? 'ok' : 'neutral'} dot>{on ? 'Enabled' : 'Off'}</Badge>
          </div>
        ))}
      </Card>

      <Card title="Legacy / Advanced" sub="Original Entropy Prime screens — nothing was removed">
        <div className={s.legacyGrid}>
          {LEGACY.map(l => (
            <button key={l.to} className={s.legacyItem} onClick={() => navigate(l.to)}>
              <span style={{ fontSize: 18 }}>{l.icon}</span>
              <div>
                <div className={s.legacyName}>{l.name}</div>
                <div className={s.legacyDesc}>{l.desc}</div>
              </div>
            </button>
          ))}
        </div>
      </Card>
    </div>
  )
}
