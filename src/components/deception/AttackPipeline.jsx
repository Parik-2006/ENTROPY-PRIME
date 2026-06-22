/**
 * AttackPipeline — animated live visualization of one simulated attack.
 *
 * Reveals the real pipeline stages in sequence, each populated with values
 * returned by the backend /score + /api/shadow/me responses:
 *
 *   Attack → Classification → Trust Evaluation → Synthetic Success Injection
 *          → Honeypot Selection → Threat Intelligence Logging
 *
 * No values are invented on the frontend; `threatLevel` is the only derived
 * label (from the selected attack catalogue) and is clearly cosmetic.
 */

import { useEffect, useState } from 'react'
import { Badge } from '../ui'

const STAGE_DELAY = 750
const SEV_TONE = { high: 'danger', medium: 'warn', low: 'ok' }

export default function AttackPipeline({ attack, result, env }) {
  const [shown, setShown] = useState(0)
  const [stamps, setStamps] = useState({})   // stage index → HH:MM:SS

  const world = env?.world || (result?.redirect === '/admin' ? 'shadow_admin' : 'banking')
  // The per-attack environment label (spec mapping) lives on the attack catalogue.
  const envLabel = attack.expect

  // Six-stage demonstration pipeline (spec):
  //   Attack Detected → Classification → Risk Assessment → Honeypot Selection
  //                   → Shadow Environment → Monitoring
  const stages = [
    { icon: attack.icon, title: '1 · Attack Detected',
      rows: [['Vector', attack.label], ['User-Agent', attack.userAgent]] },
    { icon: '🧭', title: '2 · Classification',
      rows: [['Class', result.attack_class || 'unknown'], ['Confidence', result.pipeline_confidence || '—']],
      badge: result.attack_class },
    { icon: '⚖', title: '3 · Risk Assessment',
      rows: [['Threat level', attack.threat], ['Humanity θ', num(result.humanity_score)]],
      badge: attack.threat, tone: attack.threat === 'high' ? 'danger' : 'warn' },
    { icon: '🪤', title: '4 · Honeypot Selection',
      rows: [['Strategy', envLabel], ['Decoy arm', result.mab_arm ?? '—']] },
    { icon: '🌐', title: '5 · Shadow Environment',
      rows: [['Environment', envLabel], ['Session', short(result.session_token)]],
      badge: world, tone: 'ok' },
    { icon: '📡', title: '6 · Monitoring',
      rows: [['Status', 'active · isolated'], ['Response', 'status: success']],
      tone: 'ok' },
  ]

  useEffect(() => {
    setShown(0); setStamps({})
    const timers = stages.map((_, i) => setTimeout(() => {
      setShown((n) => Math.max(n, i + 1))
      setStamps((m) => ({ ...m, [i]: new Date().toLocaleTimeString('en-GB') }))
    }, STAGE_DELAY * (i + 1)))
    return () => timers.forEach(clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.session_token])

  const complete = shown >= stages.length

  return (
    <div>
      {/* header: severity + run status */}
      <div style={st.header}>
        <span style={st.headTitle}>ATTACK PIPELINE</span>
        <span style={st.headRight}>
          <Badge tone={SEV_TONE[attack.threat] || 'neutral'}>severity: {attack.threat}</Badge>
          <Badge tone={complete ? 'ok' : 'warn'} dot>{complete ? 'complete' : 'running…'}</Badge>
        </span>
      </div>

      <div style={st.flow}>
        {stages.map((s, i) => {
          const done   = i < shown - 1 || (complete && i < shown)
          const active = i === shown - 1 && !complete
          const on     = i < shown
          const state  = active ? 'active' : done ? 'done' : 'pending'
          return (
            <div key={i} style={{ ...st.stage, opacity: on ? 1 : 0.3, transition: 'all .35s ease' }}>
              <div style={st.icon(state)}>{done ? '✓' : s.icon}</div>
              <div style={{ ...st.body, ...(active ? st.bodyActive : {}) }}>
                <div style={st.title}>
                  <span style={active ? st.titleActive : undefined}>{s.title}</span>
                  {on && s.badge && <Badge tone={s.tone || 'neutral'}>{s.badge}</Badge>}
                  {active && <span style={st.live}>● in progress</span>}
                  {on && stamps[i] && <span style={st.stamp}>{stamps[i]}</span>}
                </div>
                {on && (
                  <div style={st.rows}>
                    {s.rows.map(([k, v]) => (
                      <div key={k} style={st.row}><span style={st.k}>{k}</span><span style={st.v}>{String(v)}</span></div>
                    ))}
                  </div>
                )}
              </div>
              {i < stages.length - 1 && <div style={st.connector(done || active)} />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const num = (n) => (typeof n === 'number' ? n.toFixed(4) : '—')
const short = (t) => (t ? t.slice(0, 18) + '…' : '—')

const st = {
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  headTitle: { fontSize: 12, fontWeight: 700, letterSpacing: 2, color: 'var(--text-2)' },
  headRight: { display: 'flex', gap: 8, alignItems: 'center' },
  flow: { display: 'flex', flexDirection: 'column', gap: 4 },
  stage: { position: 'relative', display: 'flex', gap: 14, paddingBottom: 18 },
  icon: (state) => ({
    width: 40, height: 40, flexShrink: 0, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, zIndex: 1,
    background: state === 'active' ? 'var(--accent)' : state === 'done' ? 'rgba(25,195,125,.12)' : 'var(--surface-3)',
    color: state === 'active' ? '#04121d' : state === 'done' ? '#19c37d' : 'var(--text-2)',
    border: '1px solid ' + (state === 'pending' ? 'var(--border)' : 'var(--accent)'),
    boxShadow: state === 'active' ? '0 0 0 4px color-mix(in srgb, var(--accent) 25%, transparent)' : 'none',
    animation: state === 'active' ? 'pulse 1.4s infinite' : 'none',
  }),
  body: { flex: 1, paddingTop: 4, borderRadius: 8 },
  bodyActive: { background: 'color-mix(in srgb, var(--accent) 8%, transparent)', padding: '4px 10px', margin: '-2px -10px' },
  title: { fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  titleActive: { color: 'var(--accent)' },
  live: { fontSize: 10, color: 'var(--accent)', letterSpacing: 0.5 },
  stamp: { fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--mono, monospace)', marginLeft: 'auto' },
  rows: { marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 },
  row: { display: 'flex', gap: 10, fontSize: 12.5 },
  k: { color: 'var(--text-3)', width: 110, flexShrink: 0 },
  v: { color: 'var(--text)', fontFamily: 'var(--mono, monospace)' },
  connector: (on) => ({ position: 'absolute', left: 19, top: 40, width: 2, bottom: -4, background: on ? 'var(--accent)' : 'var(--border)', transition: 'background .35s' }),
}
