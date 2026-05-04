import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { submitScore, hashPassword, loginUser, registerUser } from '../services/api'
import styles from './LoginPage.module.css'

// ── Live signal bar ──────────────────────────────────────────────────────────
function SignalBar({ label, value, color = 'var(--accent)', max = 1, active = false }) {
  const pct = Math.min(value / max, 1) * 100
  return (
    <div className={styles.signalRow}>
      <span className={styles.signalLabel} style={{ color: active ? 'var(--accent)' : undefined }}>
        {label}{active ? ' ★' : ''}
      </span>
      <div className={styles.signalTrack}>
        <div className={styles.signalFill} style={{
          width: pct + '%',
          background: active ? 'var(--accent3)' : color
        }} />
      </div>
      <span className={styles.signalVal}>{(value).toFixed(3)}</span>
    </div>
  )
}

// ── Score ring ───────────────────────────────────────────────────────────────
function ScoreRing({ theta }) {
  const r     = 36
  const circ  = 2 * Math.PI * r
  const pct   = theta ?? 0
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
  const max  = Math.max(...events.map(e => e.dwell), 200)
  const step = W / Math.max(events.length - 1, 1)
  const pts  = events.map((e, i) => `${i * step},${H - (e.dwell / max) * (H - 4)}`)
  return (
    <svg width={W} height={H} className={styles.trace}>
      <polyline points={pts.join(' ')} fill="none"
        stroke="var(--accent)" strokeWidth="1.5" strokeLinejoin="round" />
      {events.slice(-1).map((_, i) => (
        <circle key={i} cx={(events.length - 1) * step}
          cy={H - (events[events.length - 1].dwell / max) * (H - 4)}
          r="3" fill="var(--accent3)" />
      ))}
    </svg>
  )
}

// ── Feature chip ─────────────────────────────────────────────────────────────
function FeatureChip({ name, selected }) {
  const shortName = name.replace('_norm', '').toUpperCase()
  return (
    <span className={styles.featureChip}
      style={{ borderColor: selected ? 'var(--accent3)' : 'var(--border)',
               color: selected ? 'var(--accent3)' : 'var(--text3)',
               background: selected ? 'rgba(0,255,163,.07)' : 'transparent' }}>
      {shortName}
    </span>
  )
}

// ── Profile build bar ────────────────────────────────────────────────────────
function ProfileProgress({ sampleCount }) {
  const MIN_STABLE = 50
  const pct = Math.min(sampleCount / MIN_STABLE, 1)
  const label = pct >= 1 ? 'PROFILE STABLE' : `BUILDING PROFILE (${sampleCount}/${MIN_STABLE})`
  const color = pct >= 1 ? 'var(--accent3)' : 'var(--accent)'
  return (
    <div className={styles.profileProgress}>
      <div className={styles.profileProgressLabel} style={{ color }}>{label}</div>
      <div className={styles.profileProgressTrack}>
        <div className={styles.profileProgressFill}
          style={{ width: (pct * 100) + '%', background: color }} />
      </div>
    </div>
  )
}

// ── All feature names ─────────────────────────────────────────────────────────
const ALL_FEATURES = ['dwell', 'flight', 'speed', 'jitter', 'accel', 'rhythm', 'pause', 'bigram']

// ── Main page ────────────────────────────────────────────────────────────────
export default function LoginPage() {
  const { login, epReady, liveTheta, getClient, selectedFeatures, liveDrift } = useAuth()

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [phase,    setPhase]    = useState('idle')
  const [result,   setResult]   = useState(null)
  const [error,    setError]    = useState('')
  const [kbStats,  setKbStats]  = useState({ avgDwell: 0, avgFlight: 0, rhythm: 0, avgPause: 0, count: 0 })
  const [ptStats,  setPtStats]  = useState({ avgSpeed: 0, avgJitter: 0, avgAccel: 0 })
  const [keyTrace, setKeyTrace] = useState([])
  const [hashInfo, setHashInfo] = useState(null)
  const [profileStats, setProfileStats] = useState(null)

  // Refresh stats on interval
  useEffect(() => {
    const id = setInterval(() => {
      const ep = getClient()
      if (!ep) return
      setKbStats(ep.getKeyboardStats())
      setPtStats(ep.getPointerStats())
      setKeyTrace([...ep.keyboard._events.slice(-40)])
      setProfileStats(ep.getProfileStats())
    }, 400)
    return () => clearInterval(id)
  }, [getClient])

  const handleSubmit = useCallback(async () => {
    if (!email || !password) { setError('Email and password required.'); return }
    if (!epReady) { setError('Biometrics engine not ready. Please wait...'); return }
    setError('')
    setPhase('scanning')
    try {
      const ep = getClient()
      if (!ep) { setError('Biometrics engine not initialized'); return }
      
      const { theta, hExp } = await ep.evaluate(password)
      
      // Validate values before submitting
      if (!isFinite(theta) || !isFinite(hExp)) {
        setError('Invalid biometric values. Please type more naturally and try again.')
        setPhase('idle')
        return
      }
      
      const latentVector    = await ep.getLatentVector()

      setPhase('authenticating')

      // Try to login first; if user doesn't exist, register them
      let authData
      try {
        authData = await loginUser({ email, plainPassword: password })
      } catch (loginErr) {
        // User doesn't exist; register them
        if (loginErr.message?.includes('Invalid email')) {
          authData = await registerUser({ email, plainPassword: password })
        } else {
          throw loginErr
        }
      }

      setPhase('hashing')

      console.log('[LoginPage] Before submitScore:', {
        theta: typeof theta, thetaVal: theta, isFinite_theta: isFinite(theta),
        hExp: typeof hExp, hExpVal: hExp, isFinite_hExp: isFinite(hExp),
        latentVectorLen: latentVector.length,
        latentFirst5: latentVector.slice(0, 5),
      })
      const scoreData = await submitScore({
        theta, hExp, latentVector,
        serverLoad: 0.4 + Math.random() * 0.3,
      })

      const hashData = await hashPassword({ plainPassword: password, theta, hExp })
      setHashInfo(hashData)

      const userData = { id: authData.user_id, email: authData.email, theta, hExp }
      login(userData, authData.session_token)

      setResult({ ...scoreData, theta, hExp })
      setPhase('done')
    } catch (e) {
      setError(e.message || 'Authentication failed')
      setPhase('error')
    }
  }, [email, password, getClient, login])

  const theta      = liveTheta ?? 0
  const hExp       = kbStats.count > 5 ? Math.min(kbStats.count / 50, 1) : 0
  const thetaColor = theta > 0.7 ? '#00ffa3' : theta > 0.4 ? '#ffb800' : '#ff3b5c'

  return (
    <div className={styles.page}>
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
            ['01', 'BIOLOGICAL GATEWAY',  'Neuromuscular signal extraction via 8-channel 1D-CNN'],
            ['02', 'RESOURCE GOVERNOR',   'RL-driven Argon2id hardening (DQN/MAB)'],
            ['03', 'OFFENSIVE DECEPTION', 'Honeypot injection + shadow sandbox routing'],
            ['04', 'SESSION WATCHDOG',    'Per-user behavioral profile + adaptive drift detection'],
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

        {/* Feature selection panel */}
        <div className={styles.featurePanel}>
          <div className={styles.featurePanelTitle}>PER-USER FEATURE SELECTION</div>
          <div className={styles.featureChips}>
            {ALL_FEATURES.map(f => (
              <FeatureChip key={f} name={f + '_norm'}
                selected={selectedFeatures.some(sf => sf.includes(f))} />
            ))}
          </div>
          <div className={styles.featureSub}>
            ★ = selected as discriminative for this user
          </div>
        </div>

        <div className={styles.tagline}>
          Moving from <em>reputation</em> to <em>biology</em>.
        </div>
      </div>

      {/* Right panel */}
      <div className={styles.right}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <div className={styles.statusDot}
              style={{ background: epReady ? 'var(--accent3)' : 'var(--text3)' }} />
            <span className={styles.statusText}>
              {epReady ? 'BIOMETRIC ENGINE ACTIVE' : 'INITIALIZING ENGINE...'}
            </span>
            {liveDrift > 0 && (
              <span className={styles.driftBadge}
                style={{ color: liveDrift > 2 ? 'var(--danger)' : 'var(--warn)' }}>
                DRIFT: {liveDrift.toFixed(2)}
              </span>
            )}
          </div>

          {/* Profile progress */}
          {profileStats && (
            <ProfileProgress sampleCount={profileStats.sampleCount} />
          )}

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
              <SignalBar label="H_EXP"   value={hExp}                    color="var(--accent)"
                active={selectedFeatures.includes('dwell_norm')} />
              <SignalBar label="DWELL"   value={kbStats.avgDwell}        color="var(--accent3)" max={300}
                active={selectedFeatures.includes('dwell_norm')} />
              <SignalBar label="FLIGHT"  value={kbStats.avgFlight}       color="#a78bfa" max={500}
                active={selectedFeatures.includes('flight_norm')} />
              <SignalBar label="RHYTHM"  value={kbStats.rhythm || 0}     color="var(--warn)" max={1}
                active={selectedFeatures.includes('rhythm_norm')} />
              <SignalBar label="JITTER"  value={ptStats.avgJitter || 0}  color="var(--warn)" max={100}
                active={selectedFeatures.includes('jitter_norm')} />
              <SignalBar label="ACCEL"   value={ptStats.avgAccel || 0}   color="#f472b6" max={500}
                active={selectedFeatures.includes('accel_norm')} />
              <div className={styles.traceWrap}>
                <TypingTrace events={keyTrace} />
              </div>
            </div>
          </div>

          {/* Form */}
          <div className={styles.form}>
            <label htmlFor="email" className={styles.label}>EMAIL</label>
            <input
              id="email"
              name="email"
              className={styles.input}
              type="email"
              placeholder="operator@entropy.io"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              autoComplete="off"
            />

            <label htmlFor="password" className={styles.label}>PASSWORD</label>
            <input
              id="password"
              name="password"
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
              {phase === 'idle'     && 'AUTHENTICATE'}
            </button>

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
                {profileStats && (
                  <div className={styles.hashRow}>
                    <span className={styles.hashLabel}>PROFILE SAMPLES</span>
                    <span className={styles.hashVal} style={{ color: 'var(--accent)' }}>
                      {profileStats.sampleCount}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className={styles.cardFooter}>
            <span>KEYSTROKES: <b>{kbStats.count}</b></span>
            <span>POINTER: <b>{ptStats.count || 0}</b></span>
            <span>DRIFT: <b style={{ color: liveDrift > 2 ? 'var(--warn)' : 'var(--accent3)' }}>
              {liveDrift.toFixed(3)}
            </b></span>
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
