/**
 * src/DefenderPanel.tsx — DEFENDER-ONLY overlay (never shown to the attacker).
 *
 * Rendered ONLY when the operator explicitly enables dev mode (?dev=1).  It is
 * a floating, collapsible overlay that surfaces the deception telemetry the
 * attacker must never see:
 *
 *   • attack classification + session token
 *   • which synthetic world the session was routed into
 *   • pages visited / API calls / canary hits (this session)
 *   • global threat-intelligence summary
 *
 * Data comes from the defender-only endpoints:
 *   GET /admin/deception/summary
 *   GET /admin/deception/events?session_token=<token>
 *
 * SAFETY: this component is gated by the caller (ShadowDashboard renders it
 * only when devMode === true).  It must NEVER be mounted on the attacker path.
 */

import React, { useEffect, useState } from 'react'
import type { ScoreResponse } from './types'
import { fetchDeceptionSessions, fetchDeceptionEvents } from './honeypotClient'

interface DefenderPanelProps {
  scoreResponse: ScoreResponse
}

const POLL_MS = 4000

export function DefenderPanel({ scoreResponse }: DefenderPanelProps) {
  const token = scoreResponse.session_token
  const [open, setOpen]       = useState(true)
  const [summary, setSummary] = useState<any | null>(null)
  const [events, setEvents]   = useState<any[]>([])
  const [err, setErr]         = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const [s, e] = await Promise.all([
          fetchDeceptionSessions(),
          fetchDeceptionEvents(token),
        ])
        if (!alive) return
        setSummary(s)
        setEvents(e.events ?? [])
        setErr(null)
      } catch (ex: any) {
        if (alive) setErr(ex?.message ?? 'offline')
      }
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [token])

  const thisSession = (summary?.sessions ?? []).find((s: any) => s.session_token === token)
  const pages = thisSession?.pages_visited ?? 0
  const apis  = thisSession?.api_calls ?? 0
  const canary = thisSession?.canary_hits ?? 0

  if (!open) {
    return (
      <button style={s.fab} onClick={() => setOpen(true)} title="Defender panel">🛡</button>
    )
  }

  return (
    <div style={s.panel}>
      <div style={s.header}>
        <span style={s.title}>🛡 DEFENDER VIEW</span>
        <button style={s.close} onClick={() => setOpen(false)}>—</button>
      </div>
      <div style={s.note}>Operator-only · invisible to the subject</div>

      {err && <div style={s.err}>telemetry: {err}</div>}

      <Section title="Classification">
        <Row k="attack_class" v={scoreResponse.attack_class ?? thisSession?.attack_class ?? '—'} accent />
        <Row k="world" v={scoreResponse.redirect === '/admin' ? 'shadow_admin' : (thisSession ? thisSession.attack_class === 'recon' ? 'shadow_admin' : 'banking' : 'banking')} />
        <Row k="session" v={token.slice(0, 22) + '…'} />
        <Row k="humanity θ" v={scoreResponse.humanity_score.toFixed(4)} />
      </Section>

      <Section title="This session">
        <Row k="pages visited" v={String(pages)} />
        <Row k="api calls" v={String(apis)} />
        <Row k="canary hits" v={String(canary)} accent={canary > 0} />
        <Row k="time in trap" v={`${thisSession?.time_spent ?? 0}s`} />
      </Section>

      <Section title="Threat intelligence">
        <Row k="total sessions" v={String(summary?.summary?.total_sessions ?? summary?.sessions?.length ?? 0)} />
        <Row k="total events" v={String(summary?.summary?.total_events ?? events.length)} />
      </Section>

      <Section title="Recent activity (this session)">
        {events.length === 0 ? (
          <div style={s.empty}>No activity recorded yet</div>
        ) : (
          events.slice(0, 8).map((e, i) => (
            <div key={i} style={s.evRow}>
              <span style={{ ...s.evType, color: e.event_type === 'canary_hit' ? '#ff5d73' : '#7dd3fc' }}>{e.event_type}</span>
              <span style={s.evDetail}>{e.detail?.path ?? e.detail?.world ?? ''}</span>
            </div>
          ))
        )}
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={s.section}>
      <div style={s.sectionTitle}>{title.toUpperCase()}</div>
      {children}
    </div>
  )
}
function Row({ k, v, accent }: { k: string; v: string; accent?: boolean }) {
  return (
    <div style={s.row}>
      <span style={s.rowK}>{k}</span>
      <span style={{ ...s.rowV, color: accent ? '#ffb800' : '#c9d6e3' }}>{v}</span>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  fab: {
    position: 'fixed', bottom: 18, right: 18, zIndex: 9999,
    width: 44, height: 44, borderRadius: '50%', cursor: 'pointer',
    background: '#0d1117', border: '1px solid #ffb80055', color: '#ffb800', fontSize: 18,
  },
  panel: {
    position: 'fixed', bottom: 18, right: 18, zIndex: 9999, width: 300,
    maxHeight: '80vh', overflowY: 'auto',
    background: 'rgba(8,11,15,0.97)', border: '1px solid #ffb80044', borderRadius: 10,
    boxShadow: '0 12px 40px rgba(0,0,0,0.5)', padding: 12,
    fontFamily: 'monospace', color: '#c9d6e3',
  },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  title: { fontSize: 11, fontWeight: 700, color: '#ffb800', letterSpacing: 1 },
  close: { background: 'none', border: 'none', color: '#6b8299', cursor: 'pointer', fontSize: 16 },
  note: { fontSize: 8, color: '#3a5068', letterSpacing: 1, marginBottom: 8 },
  err: { fontSize: 9, color: '#ff5d73', marginBottom: 6 },
  section: { background: '#111820', border: '1px solid #1e2d3d', borderRadius: 6, padding: 9, marginBottom: 8, display: 'flex', flexDirection: 'column', gap: 5 },
  sectionTitle: { fontSize: 8, letterSpacing: 1.5, color: '#3a5068', marginBottom: 3 },
  row: { display: 'flex', justifyContent: 'space-between', gap: 8 },
  rowK: { fontSize: 9, color: '#6b8299' },
  rowV: { fontSize: 10, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: 'right' },
  empty: { fontSize: 9, color: '#3a5068', textAlign: 'center', padding: 4 },
  evRow: { display: 'flex', gap: 8, alignItems: 'center' },
  evType: { fontSize: 9, width: 84, flexShrink: 0 },
  evDetail: { fontSize: 9, color: '#6b8299', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
}
