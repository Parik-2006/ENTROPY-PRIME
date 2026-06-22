/**
 * DefenderView — operator telemetry for the Deception Demo Lab.
 *
 * Everything here is read from the REAL backend threat-intelligence store
 * (framework.deception.threat_intel, mirrored to MongoDB):
 *   GET /admin/deception/sessions        — recorded shadow sessions
 *   GET /admin/deception/events?token=   — recorded attacker events
 *
 * Shows: attack type, confidence, trust, environment, pages visited, actions
 * performed, time spent, threat events and the live telemetry feed.
 */

import { useEffect, useState } from 'react'
import { getDeceptionSessions, getDeceptionEvents } from '../../services/deception'
import { Badge } from '../ui'

const POLL_MS = 3000
const fmt = (ts) => new Date((ts || 0) * 1000).toLocaleTimeString()

export default function DefenderView({ result }) {
  const token = result?.session_token
  const [session, setSession] = useState(null)
  const [events, setEvents] = useState([])
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!token) return
    let alive = true
    const tick = async () => {
      try {
        const [s, e] = await Promise.all([getDeceptionSessions(), getDeceptionEvents(token)])
        if (!alive) return
        setSession((s.sessions || []).find((x) => x.session_token === token) || null)
        setEvents(e.events || [])
        setErr(null)
      } catch (ex) { if (alive) setErr(ex.message) }
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [token])

  if (!token) return <div style={st.empty}>Launch a simulation to populate defender telemetry.</div>

  const rows = [
    ['Attack type',   result.attack_class || session?.attack_class || '—'],
    ['Confidence',    result.pipeline_confidence || '—'],
    ['Humanity θ',    typeof result.humanity_score === 'number' ? result.humanity_score.toFixed(4) : '—'],
    ['Environment',   session?.world || (result.redirect === '/admin' ? 'shadow_admin' : 'banking')],
    ['Session ID',    token.slice(0, 28) + '…'],
    ['Pages visited', session?.pages_visited ?? 0],
    ['API calls',     session?.api_calls ?? 0],
    ['Canary hits',   session?.canary_hits ?? 0],
    ['Time in env',   `${session?.time_spent ?? 0}s`],
  ]

  return (
    <div style={st.wrap}>
      <div style={st.col}>
        <div style={st.cardTitle}>Session telemetry {err && <span style={st.err}>· {err}</span>}</div>
        <div style={st.kvBox}>
          {rows.map(([k, v]) => (
            <div key={k} style={st.kv}>
              <span style={st.kvK}>{k}</span>
              <span style={st.kvV}>{String(v)}</span>
            </div>
          ))}
        </div>
        {Number(session?.canary_hits) > 0 && (
          <div style={st.canary}>⚠ Canary token accessed — high-fidelity exploitation signal.</div>
        )}
      </div>

      <div style={st.col}>
        <div style={st.cardTitle}>
          Threat events <Badge tone="ok" dot>live</Badge>
        </div>
        <div style={st.feed}>
          {events.length === 0 ? (
            <div style={st.empty}>No events recorded yet.</div>
          ) : (
            events.map((e, i) => (
              <div key={i} style={st.ev}>
                <span style={st.evTime}>{fmt(e.ts)}</span>
                <Badge tone={e.event_type === 'canary_hit' ? 'danger' : e.event_type === 'shadow_start' ? 'warn' : 'neutral'}>
                  {e.event_type}
                </Badge>
                <span style={st.evDetail}>{e.detail?.path || e.detail?.world || ''}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

const st = {
  wrap: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  col: {},
  cardTitle: { fontSize: 13, fontWeight: 600, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 },
  err: { color: 'var(--danger)', fontSize: 11 },
  kvBox: { border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' },
  kv: { display: 'flex', justifyContent: 'space-between', padding: '9px 14px', borderBottom: '1px solid var(--border)' },
  kvK: { color: 'var(--text-2)', fontSize: 13 },
  kvV: { fontSize: 13, fontWeight: 500, fontFamily: 'var(--mono, monospace)' },
  canary: { marginTop: 10, padding: '8px 12px', background: 'rgba(255,59,92,.08)', border: '1px solid rgba(255,59,92,.25)', borderRadius: 8, fontSize: 12, color: 'var(--danger)' },
  feed: { border: '1px solid var(--border)', borderRadius: 10, maxHeight: 360, overflowY: 'auto' },
  ev: { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderBottom: '1px solid var(--border)' },
  evTime: { fontSize: 11, color: 'var(--text-3)', width: 76, flexShrink: 0, fontFamily: 'var(--mono, monospace)' },
  evDetail: { fontSize: 12, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  empty: { padding: 20, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 },
}
