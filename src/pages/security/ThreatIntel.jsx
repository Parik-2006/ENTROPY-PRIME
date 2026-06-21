/**
 * ThreatIntel — "Security Events" (human-readable).
 * Presents the live security event log from TrustContext (device / drift /
 * verification / bot events) as a friendly timeline + categorized feeds, around
 * the REAL honeypot bot signatures from GET /honeypot/signatures (preserved).
 */

import { useState, useEffect } from 'react'
import { getHoneypotSignatures } from '../../services/api'
import { useTrust } from '../../context/TrustContext'
import { Card, StatTile, Badge } from '../../components/ui'
import s from './security.module.css'

const HONEYPOT_BY_ARM = { 0: 'Tarpit', 1: 'Echo', 2: 'Canary', 3: 'Shadow-Admin' }
const KIND_META = {
  risk:         { tone: 'warn',    icon: '⚠️', label: 'Risk' },
  bot:          { tone: 'danger',  icon: '🤖', label: 'Bot' },
  session:      { tone: 'neutral', icon: '🖥', label: 'Session' },
  verification: { tone: 'ok',      icon: '✅', label: 'Verification' },
}
const fmtTime = (t) => new Date(t).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })

export default function ThreatIntel() {
  const { events } = useTrust()
  const [sigs, setSigs] = useState([])
  const [error, setError] = useState(null)

  const load = () => getHoneypotSignatures().then(d => { setSigs(d.signatures || []); setError(null) }).catch(e => setError(e.message))
  useEffect(() => { load(); const id = setInterval(load, 10000); return () => clearInterval(id) }, [])

  const count = (k) => events.filter(e => e.kind === k).length

  return (
    <div className={s.grid}>
      <div className={s.summaryRow}>
        <StatTile icon="⚠️" label="Risk Events" value={count('risk')} accent="var(--gold)" sub="Behavior deviations" />
        <StatTile icon="🤖" label="Bot Events" value={count('bot') + sigs.length} accent="var(--danger)" sub="Detections & captures" />
        <StatTile icon="🖥" label="Session Events" value={count('session')} sub="Device & session" />
        <StatTile icon="✅" label="Verification Events" value={count('verification')} accent="var(--accent)" sub="Identity checks" />
      </div>

      <div className={s.twoCol}>
        <Card title="Security Events Timeline" sub="Everything Entropy Prime noticed this session" action={<Badge tone="ok" dot>live</Badge>}>
          <div className={s.timeline}>
            {events.map(e => {
              const m = KIND_META[e.kind] || KIND_META.session
              return (
                <div className={s.tlItem} key={e.id}>
                  <span className={s.tlDot} style={{ background: `var(--${m.tone === 'ok' ? 'accent' : m.tone === 'danger' ? 'danger' : m.tone === 'warn' ? 'gold' : 'text-3'})` }} />
                  <div className={s.tlTime}>{fmtTime(e.t)} · {m.icon} {m.label}</div>
                  <div className={s.tlTitle}>{e.title}</div>
                  <div className={s.tlDesc}>{e.desc}</div>
                </div>
              )
            })}
          </div>
        </Card>

        <Card title="Deception Playbook" sub="Automated responses">
          {[
            ['Credential stuffing', 'Echo honeypot', 'danger'],
            ['Brute force', 'Tarpit (slow-drip)', 'warn'],
            ['Scraping / crawler', 'Canary tokens', 'warn'],
            ['Recon / admin probe', 'Shadow-Admin sandbox', 'danger'],
            ['Identity drift', 'Re-authentication', 'ok'],
            ['Session anomaly', 'Step-up challenge', 'ok'],
          ].map(([k, v, tone]) => (
            <div className={s.kv} key={k}><span className={s.kvKey}>{k}</span><Badge tone={tone}>{v}</Badge></div>
          ))}
        </Card>
      </div>

      <Card title="Captured Bot Signatures" sub="Real honeypot captures (PHASE 3)" action={<Badge tone={error ? 'danger' : 'ok'} dot>{error ? 'backend offline' : 'polling 10s'}</Badge>}>
        {error && <div className={s.empty}>Backend unreachable — start <code>uvicorn backend.main:app</code> to stream live captures.</div>}
        {!error && !sigs.length && <div className={s.empty}>No bot signatures captured yet. Bots with θ &lt; 0.1 appear here after shadow routing.</div>}
        {sigs.map((x, i) => (
          <div className={s.feedRow} key={i}>
            <span className={s.feedTime}>{new Date((x.ts || 0) * 1000).toLocaleTimeString()}</span>
            <span className={s.feedUa}>{x.ua || 'unknown'} · {x.path || '/'}</span>
            <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Badge tone={x.theta < 0.1 ? 'danger' : 'warn'}>θ {(x.theta * 100).toFixed(0)}%</Badge>
              <Badge tone="neutral">{HONEYPOT_BY_ARM[x.arm] ?? 'Shadow'}</Badge>
            </span>
          </div>
        ))}
      </Card>
    </div>
  )
}
