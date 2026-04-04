import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { healthCheck } from '../services/api'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import styles from './DashboardPage.module.css'

// ── Sidebar ──────────────────────────────────────────────────────────────────
function Sidebar({ active }) {
  const { user, logout, trustScore } = useAuth()
  const navigate = useNavigate()

  const trustColor = trustScore > 0.7 ? '#00ffa3' : trustScore > 0.4 ? '#ffb800' : '#ff3b5c'

  return (
    <aside className={styles.sidebar}>
      <div className={styles.sideTop}>
        <div className={styles.sideLogo}>
          <span className={styles.sideLogoMark}>EP</span>
          <div>
            <div className={styles.sideLogoName}>ENTROPY PRIME</div>
            <div className={styles.sideLogoSub}>v1.0 ACTIVE</div>
          </div>
        </div>

        {/* Trust meter */}
        <div className={styles.trustMeter}>
          <div className={styles.trustLabel}>SESSION TRUST</div>
          <div className={styles.trustBar}>
            <div className={styles.trustFill}
              style={{ width: (trustScore * 100) + '%', background: trustColor }} />
          </div>
          <div className={styles.trustVal} style={{ color: trustColor }}>
            {(trustScore * 100).toFixed(1)}%
          </div>
        </div>

        <nav className={styles.nav}>
          {[
            { id: 'dashboard', label: 'DASHBOARD', icon: '◈', path: '/dashboard' },
            { id: 'threats',   label: 'THREAT INTEL', icon: '◉', path: '/threats' },
          ].map(item => (
            <button key={item.id}
              className={`${styles.navItem} ${active === item.id ? styles.navActive : ''}`}
              onClick={() => navigate(item.path)}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      <div className={styles.sideBottom}>
        <div className={styles.userChip}>
          <div className={styles.userAvatar}>{user?.email?.[0]?.toUpperCase() ?? 'U'}</div>
          <div>
            <div className={styles.userEmail}>{user?.email}</div>
            <div className={styles.userId}>{user?.id}</div>
          </div>
        </div>
        <button className={styles.logoutBtn} onClick={logout}>DISCONNECT</button>
      </div>
    </aside>
  )
}

// ── Stat card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color = 'var(--accent)', icon }) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statIcon}>{icon}</div>
      <div className={styles.statVal} style={{ color }}>{value}</div>
      <div className={styles.statLabel}>{label}</div>
      {sub && <div className={styles.statSub}>{sub}</div>}
    </div>
  )
}

// ── Phase status badge ───────────────────────────────────────────────────────
function PhaseBadge({ n, label, status }) {
  const colors = { active: 'var(--accent3)', warn: 'var(--warn)', alert: 'var(--danger)', idle: 'var(--text3)' }
  const color  = colors[status] ?? colors.idle
  return (
    <div className={styles.phaseBadge}>
      <div className={styles.phaseBadgeNum} style={{ color }}>PH{n}</div>
      <div className={styles.phaseBadgeDot} style={{ background: color, animation: status === 'active' ? 'pulse 2s infinite' : 'none' }} />
      <div className={styles.phaseBadgeLabel}>{label}</div>
      <div className={styles.phaseBadgeStatus} style={{ color }}>{status.toUpperCase()}</div>
    </div>
  )
}

// ── Live chart tooltip ───────────────────────────────────────────────────────
function ChartTip({ active, payload }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', padding: '6px 10px',
      fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text)' }}>
      θ: {payload[0]?.value?.toFixed(3)}<br />
      E_rec: {payload[1]?.value?.toFixed(4)}
    </div>
  )
}

// ── Main dashboard ───────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user, liveTheta, trustScore, anomaly, epReady, getClient } = useAuth()

  const [chartData, setChartData] = useState([])
  const [kbStats,   setKbStats]   = useState({ avgDwell: 0, avgFlight: 0, count: 0 })
  const [ptStats,   setPtStats]   = useState({ avgSpeed: 0, avgJitter: 0, count: 0 })
  const [health,    setHealth]    = useState(null)
  const [anchored,  setAnchored]  = useState(false)
  const [argonInfo, setArgonInfo] = useState(null)

  // Boot anchor
  useEffect(() => {
    if (!epReady || anchored) return
    setAnchored(true)
    // Anchor is started in background by AuthContext, just mark UI
  }, [epReady, anchored])

  // Chart update
  useEffect(() => {
    const id = setInterval(() => {
      const ep  = getClient()
      const eRec = ep?.watchdog?.lastERec ?? 0
      const theta = liveTheta ?? 0
      setChartData(prev => [...prev.slice(-60), {
        t:    new Date().toLocaleTimeString('en', { hour12: false }),
        theta: +theta.toFixed(4),
        eRec:  +eRec.toFixed(4),
      }])
      if (ep) {
        setKbStats(ep.getKeyboardStats())
        setPtStats(ep.getPointerStats())
      }
    }, 1000)
    return () => clearInterval(id)
  }, [getClient, liveTheta])

  // Health check
  useEffect(() => {
    healthCheck().then(setHealth).catch(() => setHealth({ status: 'unreachable' }))
    const id = setInterval(() => {
      healthCheck().then(setHealth).catch(() => setHealth({ status: 'unreachable' }))
    }, 15_000)
    return () => clearInterval(id)
  }, [])

  const theta = liveTheta ?? 0
  const eRec  = getClient()?.watchdog?.lastERec ?? 0

  const phaseStatus = (n) => {
    if (!epReady) return 'idle'
    if (n === 1) return theta > 0.3 ? 'active' : 'alert'
    if (n === 2) return 'active'
    if (n === 3) return theta < 0.1 ? 'alert' : 'active'
    if (n === 4) return eRec > 0.18 ? 'warn' : 'active'
  }

  return (
    <div className={styles.layout}>
      <Sidebar active="dashboard" />

      <main className={styles.main}>
        {/* Anomaly banner */}
        {anomaly && (
          <div className={styles.anomalyBanner}>
            <span>⚠ IDENTITY ANOMALY DETECTED</span>
            <span>E_rec: {anomaly.eRec?.toFixed(4)} — Trust: {(anomaly.ts * 100).toFixed(1)}%</span>
          </div>
        )}

        <div className={styles.topBar}>
          <div>
            <div className={styles.pageTitle}>BIOMETRIC DASHBOARD</div>
            <div className={styles.pageSub}>Session: {user?.id} · {new Date().toUTCString()}</div>
          </div>
          <div className={styles.serverStatus}>
            <div className={styles.serverDot}
              style={{ background: health?.status === 'ok' ? 'var(--accent3)' : 'var(--danger)' }} />
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text2)' }}>
              SERVER {health?.status?.toUpperCase() ?? '...'} · RL_STEPS: {health?.rl_steps ?? '—'}
            </span>
          </div>
        </div>

        {/* Phase status row */}
        <div className={styles.phaseRow}>
          <PhaseBadge n={1} label="BIOLOGICAL GATEWAY"  status={phaseStatus(1)} />
          <PhaseBadge n={2} label="RESOURCE GOVERNOR"   status={phaseStatus(2)} />
          <PhaseBadge n={3} label="OFFENSIVE DECEPTION" status={phaseStatus(3)} />
          <PhaseBadge n={4} label="SESSION WATCHDOG"    status={phaseStatus(4)} />
        </div>

        {/* Stat cards */}
        <div className={styles.statGrid}>
          <StatCard icon="θ" label="HUMANITY SCORE"
            value={(theta * 100).toFixed(1) + '%'}
            color={theta > 0.7 ? '#00ffa3' : theta > 0.4 ? '#ffb800' : '#ff3b5c'}
            sub={theta > 0.7 ? 'Human confirmed' : theta > 0.4 ? 'Uncertain' : 'Bot suspected'} />
          <StatCard icon="H" label="ENTROPY SCORE"
            value={(user?.hExp * 100 || 0).toFixed(1) + '%'}
            color="var(--accent)"
            sub="Password strength" />
          <StatCard icon="E" label="RECON ERROR"
            value={eRec.toFixed(4)}
            color={eRec > 0.18 ? 'var(--warn)' : 'var(--accent3)'}
            sub={eRec > 0.18 ? 'Anomaly detected' : 'Identity stable'} />
          <StatCard icon="T" label="TRUST SCORE"
            value={(trustScore * 100).toFixed(1) + '%'}
            color={trustScore > 0.7 ? '#00ffa3' : trustScore > 0.4 ? '#ffb800' : '#ff3b5c'}
            sub="Session integrity" />
          <StatCard icon="K" label="KEYSTROKES"
            value={kbStats.count}
            color="var(--accent)"
            sub={`Dwell: ${kbStats.avgDwell.toFixed(0)}ms`} />
          <StatCard icon="P" label="POINTER EVENTS"
            value={ptStats.count || 0}
            color="var(--accent)"
            sub={`Jitter: ${(ptStats.avgJitter || 0).toFixed(1)}`} />
        </div>

        {/* Charts */}
        <div className={styles.chartGrid}>
          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>HUMANITY SCORE θ — LIVE FEED</div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData}>
                <XAxis dataKey="t" tick={{ fill: 'var(--text3)', fontSize: 9, fontFamily: 'var(--mono)' }}
                  interval={10} />
                <YAxis domain={[0, 1]} tick={{ fill: 'var(--text3)', fontSize: 9, fontFamily: 'var(--mono)' }} />
                <Tooltip content={<ChartTip />} />
                <ReferenceLine y={0.7} stroke="var(--accent3)" strokeDasharray="4 2" />
                <ReferenceLine y={0.3} stroke="var(--danger)"  strokeDasharray="4 2" />
                <Line type="monotone" dataKey="theta" stroke="var(--accent)" dot={false}
                  strokeWidth={1.5} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>AUTOENCODER RECONSTRUCTION ERROR E_rec</div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData}>
                <XAxis dataKey="t" tick={{ fill: 'var(--text3)', fontSize: 9, fontFamily: 'var(--mono)' }}
                  interval={10} />
                <YAxis domain={[0, 0.4]} tick={{ fill: 'var(--text3)', fontSize: 9, fontFamily: 'var(--mono)' }} />
                <Tooltip content={<ChartTip />} />
                <ReferenceLine y={0.18} stroke="var(--warn)" strokeDasharray="4 2" />
                <Line type="monotone" dataKey="eRec" stroke="var(--accent3)" dot={false}
                  strokeWidth={1.5} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Keyboard dynamics */}
        <div className={styles.dynamicsCard}>
          <div className={styles.chartTitle}>NEUROMUSCULAR SIGNAL VECTORS</div>
          <div className={styles.dynamicsGrid}>
            <MetricRow label="AVG DWELL TIME"  value={kbStats.avgDwell.toFixed(1)}   unit="ms"    fill={Math.min(kbStats.avgDwell/300, 1)} />
            <MetricRow label="AVG FLIGHT TIME" value={kbStats.avgFlight.toFixed(1)}  unit="ms"    fill={Math.min(kbStats.avgFlight/500, 1)} />
            <MetricRow label="AVG POINTER SPEED"  value={(ptStats.avgSpeed||0).toFixed(1)}  unit="px/s" fill={Math.min((ptStats.avgSpeed||0)/1000, 1)} />
            <MetricRow label="JITTER MAGNITUDE"   value={(ptStats.avgJitter||0).toFixed(2)} unit="σ"    fill={Math.min((ptStats.avgJitter||0)/80, 1)} />
          </div>
        </div>
      </main>
    </div>
  )
}

function MetricRow({ label, value, unit, fill }) {
  return (
    <div className={styles.metricRow}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricBar}>
        <div className={styles.metricFill} style={{ width: (fill*100)+'%' }} />
      </div>
      <div className={styles.metricVal}>{value} <span>{unit}</span></div>
    </div>
  )
}
