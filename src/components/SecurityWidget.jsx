/**
 * SecurityWidget — compact "Protected by Entropy Prime" panel for the banking
 * Dashboard. Reads live signals from AuthContext (trust + humanity θ + onboarding
 * state) and links through to the full Security Center.
 */

import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Card, ProgressRing, Badge } from './ui'

function riskLevel(trust, theta) {
  const t = trust ?? 1
  const h = theta ?? 1
  if (t < 0.4 || h < 0.3) return { label: 'Elevated', tone: 'danger' }
  if (t < 0.7 || h < 0.6) return { label: 'Guarded',  tone: 'warn' }
  return { label: 'Low', tone: 'ok' }
}

export default function SecurityWidget() {
  const { trustScore, liveTheta, isProfileStable } = useAuth()
  const theta = liveTheta ?? 0
  const risk = riskLevel(trustScore, theta)

  const rows = [
    { label: 'Trust score', value: `${(trustScore * 100).toFixed(0)}%`, tone: trustScore > 0.7 ? 'ok' : trustScore > 0.4 ? 'warn' : 'danger' },
    { label: 'Risk level', value: risk.label, tone: risk.tone },
    { label: 'Session', value: isProfileStable ? 'Verified' : 'Syncing', tone: isProfileStable ? 'ok' : 'warn' },
    { label: 'Behavior', value: theta > 0.6 ? 'Human' : theta > 0.3 ? 'Uncertain' : 'Anomalous', tone: theta > 0.6 ? 'ok' : theta > 0.3 ? 'warn' : 'danger' },
  ]

  return (
    <Card
      title="Security"
      sub="Protected by Entropy Prime"
      action={<Link to="/app/security"><Badge tone="ok">Open ↗</Badge></Link>}
    >
      <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
        <ProgressRing value={trustScore} size={104} label="Trust" color="var(--accent)" />
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {rows.map(r => (
            <div key={r.label} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.04em' }}>{r.label}</span>
              <Badge tone={r.tone} dot>{r.value}</Badge>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}
