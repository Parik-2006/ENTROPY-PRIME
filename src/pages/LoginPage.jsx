import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { submitScore, hashPassword } from '../services/api'
import styles from './LoginPage.module.css'

// ── Live signal bar ─────────────────────────────────────────────────────────
function SignalBar({ label, value, color = 'var(--accent)', max = 1 }) {
  const pct = Math.min(value / max, 1) * 100
  return (
    <div className={styles.signalRow}>
      <span className={styles.signalLabel}>{label}</span>
      <div className={styles.signalTrack}>
        <div className={styles.signalFill} style={{ width: pct + '%', background: color }} />
      </div>
      <span className={styles.signalVal}>{(value).toFixed(3)}</span>
    </div>
  )
}

// ── Score ring ───────────────────────────────────────────────────────────────
function ScoreRing({ theta }) {
  const r   = 36
  const circ = 2 * Math.PI * r
  const pct  = theta ?? 0
  const color = pct > 0.7 ? '#00ffa3' : pct > 0.4 ? '#ffb800' : '#ff3b5c'
  const label = pct > 0.7 ? 'HUMAN' : pct > 0.4 ? 'UNCERTAIN' : 'SUSPECT'
  return (
    <div className={styles.ringWrap}>
      <svg width="92" height="92" viewBox="0 0 92 92">
        <circle cx="46" cy="46" r={r} fill="none" stroke="var(--border)" strokeWidth="3" />
        <circle cx="46" cy="46" r={r} fill="none"
          stroke={color} strokeWidth="3"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - pct)}
          strokeLinecap="round"
          transform="rotate(-90 46 46)"
          style={{ transition: 'stroke-dashoffset .6s ease, stroke .4s' }}
        />
        <text x="46" y="42" textAnchor="middle" fill={color}
          style={{ fontFamily: 'var(--mono)', fontSize: '13px', fontWeight: 700 }}>
          {(pct * 100).toFixed(0)}
        </text>
        <text x="46" y="56" textAnchor="middle" fill="var(--text2)"
          style={{ fontFamily: 'var(--mono)', fontSize: '7px', letterSpacing: '1px' }}>
          {label}
        </text>
      </svg>
    </div>
  )
}

// ── Typing trace ─────────────────────────────────────────────────────────────
function TypingTrace({ events }) {
  const W = 280, H = 48
  if (!events.length) return (
    <svg width={W} height={H} className={styles.trace}>
      <text x={W/2} y={H/2} textAnchor="middle" fill="var(--text3)"
        style={{ fontFamily: 'var(--mono)', fontSize: '9px' }}>
        type to begin signal capture
      </text>
    </svg>
  )
  const max = Math.max(...events.map(e => e.dwell), 200)
  const step = W / Math.max(events.length - 1, 1)
  const pts  = events.map((e, i) => `${i * step},${H - (e.dwell / max) * (H - 4)}`)
  return (
    <svg width={W} height={H} className={styles.trace}>
      <polyline points={pts.join(' ')} fill="none"
        stroke="var(--accent)" strokeWidth="1.5" strokeLinejoin="round" />
      {events.slice(-1).map((e, i) => (
        <circle key={i} cx={(events.length - 1) * step} cy={H - (e.dwell / max) * (H - 4)}
          r="3" fill="var(--accent3)" />
      ))}
    </svg>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function LoginPage() {
  const { login, epReady, liveTheta, getClient } = useAuth()

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [phase,    setPhase]    = useState('idle')  // idle | scanning | hashing | done | error
  const [result,   setResult]   = useState(null)
  const [error,    setError]    = useState('')
  const [kbStats,  setKbStats]  = useState({ avgDwell: 0, avgFlight: 0, count: 0 })
  const [ptStats,  setPtStats]  = useState({ avgSpeed: 0, avgJitter: 0 })
  const [keyTrace, setKeyTrace] = useState([])
  const [hashInfo, setHashInfo] = useState(null)
  const [tick,     setTick]     = useState(0)

  // Refresh stats on interval
  useEffect(() => {
    const id = setInterval(() => {
      const ep = getClient()
      if (!ep) return
      setKbStats(ep.getKeyboardStats())
      setPtStats(ep.getPointerStats())
      setKeyTrace([...ep.keyboard._events.slice(-40)])
      setTick(t => t + 1)
    }, 400)
    return () => clearInterval(id)
  }, [getClient])

  const handleSubmit = useCallback(async () => {
    if (!email || !password) { setError('Email and password required.'); return }
    setError('')
    setPhase('scanning')
    try {
      const ep = getClient()
      const { theta, hExp } = await ep.evaluate(password)

      // Get latent vector for token binding
      const latentVector = await ep.getLatentVector()

      setPhase('hashing')

      // Phase 2: RL-governor selects Argon2id params
      const scoreData = await submitScore({
        theta, hExp, latentVector,
        serverLoad: 0.4 + Math.random() * 0.3,
      })

      // Hash password with selected params
      const hashData = await hashPassword({ plainPassword: password, theta, hExp })
      setHashInfo(hashData)

      // Save session
      const userData = { id: 'usr_' + Date.now(), email, theta, hExp }
      login(userData, scoreData.session_token)

      setResult({ ...scoreData, theta, hExp })
      setPhase('done')
    } catch (e) {
      setError(e.message || 'Authentication failed')
      setPhase('error')
    }
  }, [email, password, getClient, login])

  const theta    = liveTheta ?? 0
  const hExp     = kbStats.count > 5 ? Math.min(kbStats.count / 50, 1) : 0
  const thetaColor = theta > 0.7 ? '#00ffa3' : theta > 0.4 ? '#ffb800' : '#ff3b5c'

  return (
    <div className={styles.page}>
      {/* Scanline effect */}
      <div className={styles.scanline} />

      {/* Left panel: branding */}
      <div className={styles.left}>
        <div className={styles.brand}>
          <div className={styles.logo}>EP</div>
          <div>
            <div className={styles.brandName}>ENTROPY PRIME</div>
            <div className={styles.brandSub}>Zero-Trust Biometric Auth</div>
          </div>
        </div>

        <div className={styles.phases}>
          {[
            ['01', 'BIOLOGICAL GATEWAY',  'Neuromuscular signal extraction via 1D-CNN'],
            ['02', 'RESOURCE GOVERNOR',   'RL-driven Argon2id hardening (PPO/DQN)'],
            ['03', 'OFFENSIVE DECEPTION', 'Honeypot injection + shadow sandbox routing'],
            ['04', 'SESSION WATCHDOG',    'Continuous autoencoder identity verification'],
          ].map(([n, title, desc]) => (
            <div key={n} className={styles.phaseItem}>
              <span className={styles.phaseNum}>{n}</span>
              <div>
                <div className={styles.phaseTitle}>{title}</div>
                <div className={styles.phaseDesc}>{desc}</div>
              </div>
            </div>
          ))}
        </div>

        <div className={styles.tagline}>
          Moving from <em>reputation</em> to <em>biology</em>.
        </div>
      </div>

      {/* Right panel: login form + live signals */}
      <div className={styles.right}>
        <div className={styles.card}>
          {/* Header */}
          <div className={styles.cardHeader}>
            <div className={styles.statusDot} style={{ background: epReady ? 'var(--accent3)' : 'var(--text3)' }} />
            <span className={styles.statusText}>
              {epReady ? 'BIOMETRIC ENGINE ACTIVE' : 'INITIALIZING ENGINE...'}
            </span>
          </div>

          {/* Live signal panel */}
          <div className={styles.signalPanel}>
            <div className={styles.signalLeft}>
              <ScoreRing theta={theta} />
              <div className={styles.signalMeta}>
                <span className={styles.metaLabel}>θ HUMANITY</span>
                <span className={styles.metaVal} style={{ color: thetaColor }}>
                  {(theta * 100).toFixed(1)}%
                </span>
              </div>
            </div>
            <div className={styles.signalRight}>
              <SignalBar label="H_EXP"    value={hExp}                   color="var(--accent)" />
              <SignalBar label="DWELL"    value={kbStats.avgDwell}       color="var(--accent3)" max={300} />
              <SignalBar label="FLIGHT"   value={kbStats.avgFlight}      color="#a78bfa"        max={500} />
              <SignalBar label="JITTER"   value={ptStats.avgJitter || 0} color="var(--warn)"    max={100} />
              <div className={styles.traceWrap}>
                <TypingTrace events={keyTrace} />
              </div>
            </div>
          </div>

          {/* Form */}
          <div className={styles.form}>
            <label className={styles.label}>EMAIL</label>
            <input
              className={styles.input}
              type="email"
              placeholder="operator@entropy.io"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              autoComplete="off"
            />

            <label className={styles.label}>PASSWORD</label>
            <input
              className={styles.input}
              type="password"
              placeholder="••••••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            />

            {error && <div className={styles.errorMsg}>{error}</div>}

            <button
              className={styles.submitBtn}
              onClick={handleSubmit}
              disabled={phase === 'scanning' || phase === 'hashing' || !epReady}
            >
              {phase === 'scanning' && <><Spinner /> ANALYZING BIOMETRICS</>}
              {phase === 'hashing'  && <><Spinner /> COMPUTING ARGON2ID</>}
              {phase === 'done'     && '✓ AUTHENTICATED'}
              {phase === 'error'    && 'RETRY AUTHENTICATION'}
              {(phase === 'idle')   && 'AUTHENTICATE'}
            </button>

            {/* Hash result info */}
            {hashInfo && (
              <div className={styles.hashInfo}>
                <div className={styles.hashRow}>
                  <span className={styles.hashLabel}>ARGON2 PRESET</span>
                  <span className={styles.hashVal} style={{ color: actionColor(hashInfo.action) }}>
                    {hashInfo.action?.toUpperCase()}
                  </span>
                </div>
                <div className={styles.hashRow}>
                  <span className={styles.hashLabel}>MEMORY</span>
                  <span className={styles.hashVal}>{(hashInfo.argon2_params?.m / 1024).toFixed(0)} MB</span>
                </div>
                <div className={styles.hashRow}>
                  <span className={styles.hashLabel}>HASH TIME</span>
                  <span className={styles.hashVal}>{hashInfo.elapsed_ms?.toFixed(0)} ms</span>
                </div>
                <div className={styles.hashRow}>
                  <span className={styles.hashLabel}>SHADOW MODE</span>
                  <span className={styles.hashVal} style={{ color: result?.shadow_mode ? 'var(--danger)' : 'var(--accent3)' }}>
                    {result?.shadow_mode ? 'BOT ROUTED' : 'DISABLED'}
                  </span>
                </div>
              </div>
            )}
          </div>

          <div className={styles.cardFooter}>
            <span>KEYSTROKES CAPTURED: <b>{kbStats.count}</b></span>
            <span>POINTER SAMPLES: <b>{ptStats.count || 0}</b></span>
          </div>
        </div>
      </div>
    </div>
  )
}

function Spinner() {
  return <span style={{
    display: 'inline-block', width: 12, height: 12,
    border: '2px solid var(--bg)', borderTop: '2px solid currentColor',
    borderRadius: '50%', animation: 'spin .7s linear infinite', marginRight: 8,
  }} />
}

function actionColor(action) {
  return { economy: '#00ffa3', standard: 'var(--accent)', hard: 'var(--warn)', punisher: 'var(--danger)' }[action] ?? 'var(--text)'
}
