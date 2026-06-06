/**
 * src/App.tsx — Root component for the Entropy Prime Honeypot UI.
 *
 * Route logic (no react-router — single page, state-driven):
 *
 *   idle      → ScoreProbe          (fires /score, waits for response)
 *   loading   → loading spinner
 *   human     → HumanConfirmed      (θ ≥ 0.3, shadow_mode=false)
 *   shadow    → ShadowDashboard     (shadow_mode=true → full deception UI)
 *   error     → ErrorView
 *
 * This app is a standalone diagnostic tool for the Stage 2 pipeline.
 * It is NOT a replacement for the main app (src/App.jsx). It runs on
 * port 3001 and can be embedded as an iframe or loaded directly.
 *
 * devMode is controlled via ?dev=1 query param.
 */

import React, { useCallback, useState } from 'react'
import type { ScoreResponse } from './types'
import { runScore } from './honeypotClient'
import { ShadowDashboard } from './ShadowDashboard'

type AppState = 'idle' | 'loading' | 'human' | 'shadow' | 'error'

const DEV_MODE = new URLSearchParams(window.location.search).get('dev') === '1'

export default function App() {
  const [state,    setState]    = useState<AppState>('idle')
  const [response, setResponse] = useState<ScoreResponse | null>(null)
  const [errorMsg, setErrorMsg] = useState('')

  // Probe parameters (user-adjustable in dev mode)
  const [theta,  setTheta]  = useState(0.05)  // low = bot-like
  const [hExp,   setHExp]   = useState(0.5)
  const [load,   setLoad]   = useState(0.4)

  const probe = useCallback(async () => {
    setState('loading')
    setErrorMsg('')
    try {
      const res = await runScore({
        theta,
        h_exp:       hExp,
        server_load: load,
        latent_vector: Array(32).fill(0).map(() => Math.random() * 0.1),
      })
      setResponse(res)
      setState(res.shadow_mode ? 'shadow' : 'human')
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e))
      setState('error')
    }
  }, [theta, hExp, load])

  const reset = useCallback(() => {
    setState('idle')
    setResponse(null)
    setErrorMsg('')
  }, [])

  // ── Shadow mode: hand off to full deception UI ───────────────────────────
  if (state === 'shadow' && response) {
    return (
      <div>
        {DEV_MODE && (
          <div style={styles.resetBar}>
            <span style={styles.resetLabel}>Shadow mode active</span>
            <button style={styles.resetBtn} onClick={reset}>← Reset</button>
          </div>
        )}
        <ShadowDashboard scoreResponse={response} devMode={DEV_MODE} />
      </div>
    )
  }

  // ── All other states: probe UI ───────────────────────────────────────────
  return (
    <div style={styles.page}>
      <div style={styles.card}>
        {/* Header */}
        <div style={styles.cardHeader}>
          <div style={styles.logo}>EP</div>
          <div>
            <div style={styles.title}>Honeypot UI — Stage 2 Probe</div>
            <div style={styles.subtitle}>
              Fires /score and routes output to shadow deception layer
            </div>
          </div>
        </div>

        {/* Controls */}
        <div style={styles.body}>
          {DEV_MODE && (
            <div style={styles.controls}>
              <div style={styles.controlsTitle}>PROBE PARAMETERS</div>
              <SliderRow
                label="θ (humanity)"
                value={theta} min={0} max={1} step={0.01}
                hint="< 0.1 = definite bot → shadow route"
                onChange={setTheta}
                color={theta < 0.1 ? '#ff3b5c' : theta < 0.3 ? '#ffb800' : '#00ffa3'}
              />
              <SliderRow
                label="h_exp (entropy)"
                value={hExp} min={0} max={1} step={0.01}
                hint="password entropy signal"
                onChange={setHExp}
                color="#00e5ff"
              />
              <SliderRow
                label="server_load"
                value={load} min={0} max={1} step={0.01}
                hint="> 0.85 caps preset at STANDARD"
                onChange={setLoad}
                color="#a78bfa"
              />
            </div>
          )}

          {state === 'idle' && (
            <div style={styles.probeSection}>
              {!DEV_MODE && (
                <p style={styles.hint}>
                  Click below to run the 4-stage pipeline. <br />
                  With low θ the response activates shadow mode.
                </p>
              )}
              <button style={styles.probeBtn} onClick={probe}>
                Run /score Pipeline
              </button>
            </div>
          )}

          {state === 'loading' && (
            <div style={styles.loading}>
              <Spinner />
              <span>Running pipeline…</span>
            </div>
          )}

          {state === 'human' && response && (
            <HumanConfirmed response={response} onReset={reset} />
          )}

          {state === 'error' && (
            <div style={styles.error}>
              <div style={styles.errorTitle}>Pipeline Error</div>
              <code style={styles.errorMsg}>{errorMsg}</code>
              <button style={styles.resetBtn} onClick={reset}>Retry</button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={styles.footer}>
          Entropy Prime v3.2 · Stage 2: Offensive Deception · Shadow Sandbox
          {DEV_MODE && <span style={{ color: '#ffb800', marginLeft: 8 }}>DEV MODE</span>}
        </div>
      </div>
    </div>
  )
}

// ── HumanConfirmed ────────────────────────────────────────────────────────────

function HumanConfirmed({ response, onReset }: { response: ScoreResponse; onReset: () => void }) {
  return (
    <div style={styles.humanBox}>
      <div style={styles.humanIcon}>✓</div>
      <div style={styles.humanTitle}>Human Confirmed</div>
      <div style={styles.humanSub}>shadow_mode = false · No decoys injected</div>
      <div style={styles.humanStats}>
        <Stat label="θ" value={(response.humanity_score * 100).toFixed(1) + '%'} color="#00ffa3" />
        <Stat label="preset" value={response.action_label} color="#00e5ff" />
        <Stat label="confidence" value={response.pipeline_confidence} color="#a78bfa" />
      </div>
      <button style={{ ...styles.resetBtn, marginTop: 16 }} onClick={onReset}>
        Run Again
      </button>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontFamily: 'monospace', fontSize: 18, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontFamily: 'monospace', fontSize: 8, color: '#6b8299', letterSpacing: 1.5 }}>
        {label.toUpperCase()}
      </div>
    </div>
  )
}

// ── SliderRow ─────────────────────────────────────────────────────────────────

function SliderRow({
  label, value, min, max, step, hint, onChange, color,
}: {
  label: string; value: number; min: number; max: number; step: number
  hint: string; onChange: (v: number) => void; color: string
}) {
  return (
    <div style={styles.sliderRow}>
      <div style={styles.sliderTop}>
        <span style={styles.sliderLabel}>{label}</span>
        <span style={{ ...styles.sliderVal, color }}>{value.toFixed(2)}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(+e.target.value)}
        style={styles.sliderInput}
      />
      <div style={styles.sliderHint}>{hint}</div>
    </div>
  )
}

function Spinner() {
  return (
    <div style={{
      width: 20, height: 20,
      border: '2px solid #1e2d3d', borderTopColor: '#00e5ff',
      borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
    }} />
  )
}

// ── Inline styles ─────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
    background: '#080b0f', padding: 24,
  },
  card: {
    width: '100%', maxWidth: 520,
    background: '#0d1117', border: '1px solid #1e2d3d',
    borderRadius: 12, overflow: 'hidden',
  },
  cardHeader: {
    display: 'flex', alignItems: 'center', gap: 14,
    padding: '16px 20px', borderBottom: '1px solid #1e2d3d',
    background: '#111820',
  },
  logo: {
    width: 40, height: 40, border: '1.5px solid #00e5ff', flexShrink: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'monospace', fontSize: 12, fontWeight: 700, color: '#00e5ff',
  },
  title:    { fontSize: 14, fontWeight: 700, letterSpacing: 1.5 },
  subtitle: { fontSize: 10, color: '#6b8299', marginTop: 2 },
  body: { padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 },

  controls: {
    background: '#080b0f', border: '1px solid #1e2d3d',
    borderRadius: 8, padding: 16,
    display: 'flex', flexDirection: 'column', gap: 14,
  },
  controlsTitle: {
    fontFamily: 'monospace', fontSize: 8, letterSpacing: 2, color: '#3a5068',
  },

  sliderRow:  { display: 'flex', flexDirection: 'column', gap: 4 },
  sliderTop:  { display: 'flex', justifyContent: 'space-between' },
  sliderLabel:{ fontFamily: 'monospace', fontSize: 10, color: '#6b8299' },
  sliderVal:  { fontFamily: 'monospace', fontSize: 11, fontWeight: 700 },
  sliderInput:{ width: '100%', accentColor: '#00e5ff' },
  sliderHint: { fontFamily: 'monospace', fontSize: 8, color: '#3a5068' },

  probeSection: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '8px 0',
  },
  hint: { textAlign: 'center', fontSize: 12, color: '#6b8299', lineHeight: 1.7 },
  probeBtn: {
    padding: '12px 32px', background: '#00e5ff', color: '#080b0f',
    border: 'none', borderRadius: 6, fontFamily: 'monospace',
    fontSize: 12, fontWeight: 700, letterSpacing: 2, cursor: 'pointer',
  },

  loading: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    gap: 12, padding: 24,
    fontFamily: 'monospace', fontSize: 11, color: '#6b8299',
  },

  humanBox: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
    padding: '20px 0',
  },
  humanIcon: {
    width: 56, height: 56, borderRadius: '50%',
    background: 'rgba(0,255,163,.1)', border: '2px solid #00ffa3',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 22, color: '#00ffa3',
  },
  humanTitle: { fontSize: 16, fontWeight: 700, color: '#00ffa3' },
  humanSub:   { fontSize: 11, color: '#6b8299', fontFamily: 'monospace' },
  humanStats: { display: 'flex', gap: 32, marginTop: 8 },

  error: {
    background: 'rgba(255,59,92,.06)', border: '1px solid rgba(255,59,92,.2)',
    borderRadius: 8, padding: 16,
    display: 'flex', flexDirection: 'column', gap: 10,
  },
  errorTitle: { fontFamily: 'monospace', fontSize: 11, color: '#ff3b5c', fontWeight: 700 },
  errorMsg: {
    fontFamily: 'monospace', fontSize: 10, color: '#c9d6e3',
    background: '#080b0f', padding: '8px 12px', borderRadius: 4,
    whiteSpace: 'pre-wrap', wordBreak: 'break-all',
  },

  resetBar: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '8px 16px', background: '#0d1117', borderBottom: '1px solid #1e2d3d',
    position: 'sticky', top: 0, zIndex: 10,
  },
  resetLabel: { fontFamily: 'monospace', fontSize: 10, color: '#ffb800' },
  resetBtn: {
    padding: '6px 14px', border: '1px solid #1e2d3d', background: 'none',
    borderRadius: 4, fontFamily: 'monospace', fontSize: 10,
    color: '#c9d6e3', cursor: 'pointer',
  },

  footer: {
    padding: '10px 20px', borderTop: '1px solid #1e2d3d',
    background: '#111820',
    fontFamily: 'monospace', fontSize: 9,
    color: '#3a5068', letterSpacing: 1,
  },
}
