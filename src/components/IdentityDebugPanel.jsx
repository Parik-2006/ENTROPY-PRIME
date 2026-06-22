/**
 * IdentityDebugPanel — TEMPORARY developer diagnostics for behavioral identity.
 *
 * Shows the live frozen-template identity scoring: Typing / Digraph / Mouse
 * similarity and the final Identity Score + zone. For testing only — rendered
 * in AppShell ONLY when the URL has ?dev=1.
 *
 * Expected demo:
 *   Owner typing      → Identity Score 90–100  (Trusted)
 *   Different person  → Identity Score < 60     (Re-auth) → modal fires
 */

import { useAuth } from '../context/AuthContext'
import { useTrust } from '../context/TrustContext'

const ZONE_COLOR = { trusted: '#19c37d', monitor: '#e7b008', reauth: '#ff4d4f' }
const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)

export default function IdentityDebugPanel() {
  const { identity, profileStats, reEnroll, trustScore } = useAuth()
  const { simulateIdentityDeviation, demoMode, confidence } = useTrust()
  const enrolled = profileStats?.enrolled

  const score = identity?.score
  const zone  = identity?.zone ?? (enrolled ? 'monitor' : 'enrolling')
  const color = ZONE_COLOR[zone] || '#7a8699'

  return (
    <div style={st.wrap}>
      <div style={st.head}>
        <span style={st.title}>🔬 IDENTITY DEBUG</span>
        <span style={st.devTag}>{demoMode ? 'DEMO' : 'dev'}</span>
      </div>

      {/* Presenter control — the safe way to show the re-auth modal on cue */}
      <button style={st.deviationBtn} onClick={simulateIdentityDeviation}>
        ⚠ Simulate Identity Deviation
      </button>
      {demoMode && (
        <div style={st.demoBadge}>DEMO MODE · confidence pinned at {confidence}</div>
      )}

      {!enrolled ? (
        <div style={st.note}>Collecting enrollment template… keep typing (~30 keys).</div>
      ) : !identity ? (
        <div style={st.note}>Template frozen. Type to score live identity.</div>
      ) : (
        <>
          <div style={st.scoreBox}>
            <div style={{ ...st.score, color }}>{score}</div>
            <div style={{ ...st.zone, color }}>{zone.toUpperCase()}{identity.corroborated ? ' · CORROBORATED' : ''}</div>
          </div>
          <Bar label="Typing"          v={identity.typingSim}  />
          <Bar label="Digraph"         v={identity.digraphSim} />
          <Bar label="Digraph profile" v={identity.digraphProfileSim} />
          <Bar label="Trigraph"        v={identity.trigraphSim} />
          <Bar label="Dwell"           v={identity.dwellSim} />
          <Bar label="Burst"           v={identity.burstSim} />
          <Bar label="Backspace"       v={identity.backspaceSim} />
          <Bar label="Spacebar"        v={identity.spacebarSim} />
          <Bar label="Phrase"          v={identity.phraseSim} />
          <Bar label="Mouse"           v={identity.mouseSim}   />
          <div style={st.row}><span style={st.k}>Confidence (smoothed)</span><span style={{ ...st.v, color }}>{score}/100</span></div>
          <div style={st.row}><span style={st.k}>Raw score (instant)</span><span style={st.v}>{identity.raw ?? '—'}</span></div>
          <div style={st.row}><span style={st.k}>Drifting signals</span><span style={st.v}>{identity.driftCount ?? 0}</span></div>
          <div style={st.row}><span style={st.k}>Suspicion</span><span style={st.v}>{identity.suspicion ?? 0} / 8</span></div>
          <div style={st.row}><span style={st.k}>Trust (effective)</span><span style={st.v}>{pct(trustScore)}</span></div>
          {identity.reauth && <div style={st.reauth}>RE-AUTH triggered (sustained pattern)</div>}
        </>
      )}

      <button style={st.btn} onClick={reEnroll}>↻ Re-enroll (clear template)</button>
      <div style={st.zones}>80–100 Trusted · 60–80 Monitor · &lt;60 Re-auth</div>
    </div>
  )
}

function Bar({ label, v }) {
  const w = Math.max(0, Math.min(1, v ?? 0)) * 100
  const c = w >= 80 ? '#19c37d' : w >= 60 ? '#e7b008' : '#ff4d4f'
  return (
    <div style={st.barRow}>
      <div style={st.barTop}><span style={st.k}>{label}</span><span style={st.v}>{pct(v)}</span></div>
      <div style={st.track}><div style={{ ...st.fill, width: `${w}%`, background: c }} /></div>
    </div>
  )
}

const st = {
  wrap: { position: 'fixed', bottom: 16, right: 16, zIndex: 9998, width: 280,
    background: 'rgba(10,14,20,0.97)', border: '1px solid #2a3a4d', borderRadius: 10,
    padding: 14, color: '#cdd9e5', fontFamily: 'var(--mono, monospace)', boxShadow: '0 12px 40px rgba(0,0,0,.5)' },
  head: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  title: { fontSize: 11, fontWeight: 700, letterSpacing: 1, color: '#8ab4f8' },
  devTag: { fontSize: 8, color: '#5a6b7d', border: '1px solid #2a3a4d', borderRadius: 4, padding: '1px 5px' },
  deviationBtn: { width: '100%', padding: '9px', marginBottom: 8, background: 'rgba(255,77,79,.14)', border: '1px solid rgba(255,77,79,.45)', borderRadius: 7, color: '#ff8589', cursor: 'pointer', fontSize: 12, fontWeight: 700, letterSpacing: 0.3 },
  demoBadge: { fontSize: 9, color: '#19c37d', textAlign: 'center', marginBottom: 8, letterSpacing: 0.5 },
  note: { fontSize: 11, color: '#7a8699', padding: '8px 0' },
  scoreBox: { textAlign: 'center', marginBottom: 10 },
  score: { fontSize: 38, fontWeight: 800, lineHeight: 1 },
  zone: { fontSize: 10, letterSpacing: 2, marginTop: 2 },
  barRow: { marginBottom: 8 },
  barTop: { display: 'flex', justifyContent: 'space-between', marginBottom: 3 },
  track: { height: 6, background: '#1a2533', borderRadius: 99, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 99, transition: 'width .3s' },
  row: { display: 'flex', justifyContent: 'space-between', marginTop: 8, paddingTop: 8, borderTop: '1px solid #1d2937' },
  k: { fontSize: 10, color: '#7a8699' },
  v: { fontSize: 11, color: '#cdd9e5' },
  reauth: { marginTop: 8, padding: '6px 8px', background: 'rgba(255,77,79,.12)', border: '1px solid rgba(255,77,79,.3)', borderRadius: 6, fontSize: 10, color: '#ff7875', textAlign: 'center' },
  btn: { marginTop: 12, width: '100%', padding: '7px', background: '#16202c', border: '1px solid #2a3a4d', borderRadius: 6, color: '#cdd9e5', cursor: 'pointer', fontSize: 11 },
  zones: { marginTop: 8, fontSize: 8, color: '#5a6b7d', textAlign: 'center', letterSpacing: 0.5 },
}
