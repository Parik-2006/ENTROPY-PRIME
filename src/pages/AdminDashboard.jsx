import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { healthCheck } from '../services/api'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, AreaChart, Area, BarChart, Bar } from 'recharts'
import ThreatMap from '../components/ThreatMap'
import styles from './AdminDashboard.module.css'

// ── Sidebar ────────────────────────────────────────────────────────────────
function Sidebar({ active }) {
  const { user, logout, trustScore } = useAuth()
  const navigate = useNavigate()
  const trustColor = trustScore > 0.7 ? '#00ffa3' : trustScore > 0.4 ? '#ffb800' : '#ff3b5c'

  const navItems = [
    { id: 'admin',         label: 'ADMIN OVERVIEW', icon: '⬡', path: '/admin' },
    { id: 'profile-build', label: 'PROFILE BUILD',  icon: '◈', path: '/profile-build' },
    { id: 'dashboard',     label: 'DASHBOARD',      icon: '◈', path: '/dashboard' },
    { id: 'threats',       label: 'THREAT INTEL',   icon: '◉', path: '/threats' },
    { id: 'sites',         label: 'SITE MGMT',      icon: '◫', path: '/sites' },
  ]

  return (
    <aside className={styles.sidebar}>
      <div className={styles.sideTop}>
        <div className={styles.sideLogo}>
          <span className={styles.sideLogoMark}>EP</span>
          <div>
            <div className={styles.sideLogoName}>ENTROPY PRIME</div>
            <div className={styles.sideLogoSub}>ADMIN CONSOLE</div>
          </div>
        </div>

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
          {navItems.map(item => (
            <button key={item.id}
              className={`${styles.navItem} ${active === item.id ? styles.navActive : ''}`}
              onClick={() => navigate(item.path)}>
              <span className={styles.navIcon}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        {/* System health block */}
        <div className={styles.sysBlock}>
          <div className={styles.sysBlockTitle}>SYSTEM HEALTH</div>
          {[
            { label: 'CNN Engine',   val: 99.2, unit: '%' },
            { label: 'DQN Governor', val: 97.8, unit: '%' },
            { label: 'MAB Agent',    val: 100,  unit: '%' },
            { label: 'Watchdog PPO', val: 98.5, unit: '%' },
          ].map(s => (
            <div key={s.label} className={styles.sysRow}>
              <span className={styles.sysLabel}>{s.label}</span>
              <div className={styles.sysBar}>
                <div className={styles.sysFill}
                  style={{ width: s.val + '%', background: s.val > 99 ? 'var(--accent3)' : s.val > 95 ? 'var(--accent)' : 'var(--warn)' }} />
              </div>
              <span className={styles.sysVal} style={{ color: s.val > 99 ? 'var(--accent3)' : 'var(--accent)' }}>
                {s.val}%
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.sideBottom}>
        <div className={styles.userChip}>
          <div className={styles.userAvatar}>{user?.email?.[0]?.toUpperCase() ?? 'A'}</div>
          <div>
            <div className={styles.userRole}>ADMIN</div>
            <div className={styles.userEmail}>{user?.email}</div>
          </div>
        </div>
        <button className={styles.logoutBtn} onClick={logout}>DISCONNECT</button>
      </div>
    </aside>
  )
}

// ── Kpi Card ───────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, delta, color = 'var(--accent)', icon, sparkData }) {
  const isUp = delta > 0
  return (
    <div className={styles.kpiCard}>
      <div className={styles.kpiTop}>
        <div className={styles.kpiIcon}>{icon}</div>
        {delta !== undefined && (
          <div className={styles.kpiDelta} style={{ color: isUp ? 'var(--danger)' : 'var(--accent3)' }}>
            {isUp ? '▲' : '▼'} {Math.abs(delta)}%
          </div>
        )}
      </div>
      <div className={styles.kpiVal} style={{ color }}>{value}</div>
      <div className={styles.kpiLabel}>{label}</div>
      {sub  && <div className={styles.kpiSub}>{sub}</div>}
      {sparkData && (
        <div className={styles.kpiSpark}>
          <ResponsiveContainer width="100%" height={36}>
            <AreaChart data={sparkData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <Area type="monotone" dataKey="v" stroke={color} fill={color}
                fillOpacity={0.08} strokeWidth={1.2} dot={false} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ── Security Health Score ──────────────────────────────────────────────────
function HealthRing({ score, label, size = 80 }) {
  const r     = (size / 2) - 8
  const circ  = 2 * Math.PI * r
  const color = score > 80 ? '#00ffa3' : score > 60 ? '#ffb800' : '#ff3b5c'
  return (
    <div className={styles.healthRing} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none"
          stroke="var(--border)" strokeWidth={4} />
        <circle cx={size/2} cy={size/2} r={r} fill="none"
          stroke={color} strokeWidth={4}
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - score / 100)}
          strokeLinecap="round"
          transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
        <text x={size/2} y={size/2 - 4} textAnchor="middle"
          fill={color} style={{ fontFamily: 'var(--mono)', fontSize: size * 0.18, fontWeight: 700 }}>
          {score}
        </text>
        <text x={size/2} y={size/2 + 11} textAnchor="middle"
          fill="var(--text3)" style={{ fontFamily: 'var(--mono)', fontSize: size * 0.1, letterSpacing: 1 }}>
          {label}
        </text>
      </svg>
    </div>
  )
}

// ── Alert Row ──────────────────────────────────────────────────────────────
function AlertRow({ sev, msg, ts, site }) {
  const colors = { critical: '#ff3b5c', high: '#ffb800', medium: 'var(--accent)', low: 'var(--accent3)' }
  return (
    <div className={styles.alertRow} style={{ borderLeft: `2px solid ${colors[sev]}` }}>
      <div className={styles.alertSev} style={{ color: colors[sev] }}>{sev.toUpperCase()}</div>
      <div className={styles.alertMsg}>{msg}</div>
      <div className={styles.alertSite}>{site}</div>
      <div className={styles.alertTs}>{ts}</div>
    </div>
  )
}

// ── Generate fake time-series ──────────────────────────────────────────────
function genSeries(n, base, variance) {
  return Array.from({ length: n }, (_, i) => ({
    t: `${String(new Date(Date.now() - (n - i) * 60000).getHours()).padStart(2,'0')}:${String(new Date(Date.now() - (n - i) * 60000).getMinutes()).padStart(2,'0')}`,
    v: Math.max(0, base + (Math.random() - 0.5) * variance)
  }))
}

const SAMPLE_ALERTS = [
  { sev: 'critical', msg: 'Credential stuffing wave — 8,420 attempts/min', site: 'api.acme.io',    ts: '14:32:01' },
  { sev: 'high',     msg: 'Bot cluster detected — θ < 0.05 × 43 IPs',      site: 'auth.stripe.io', ts: '14:31:58' },
  { sev: 'high',     msg: 'Shadow sandbox activated — MAB arm 2',           site: 'login.shopify',  ts: '14:31:47' },
  { sev: 'medium',   msg: 'Behavioral drift spike — user uid_8821',         site: 'admin.vercel',   ts: '14:31:22' },
  { sev: 'medium',   msg: 'DQN switched preset: standard → hard',           site: 'api.acme.io',    ts: '14:30:55' },
  { sev: 'low',      msg: 'PPO watchdog: passive_reauth issued × 12',       site: 'auth.stripe.io', ts: '14:30:40' },
  { sev: 'low',      msg: 'Feature selection updated for uid_4501',          site: 'login.shopify',  ts: '14:30:11' },
]

// ── Main ───────────────────────────────────────────────────────────────────
export default function AdminDashboard() {
  const { user, trustScore, anomaly } = useAuth()

  const [health,       setHealth]       = useState(null)
  const [thetaSeries,  setThetaSeries]  = useState(() => genSeries(30, 0.76, 0.18))
  const [requestSeries,setRequestSeries]= useState(() => genSeries(30, 3400, 1200))
  const [botRateSeries,setBotRateSeries]= useState(() => genSeries(30, 0.08, 0.06))
  const [alerts,       setAlerts]       = useState(SAMPLE_ALERTS)
  const [secScores]    = useState({
    overall:    94,
    biological: 97,
    governor:   91,
    deception:  96,
    watchdog:   89,
  })

  // Health check
  useEffect(() => {
    healthCheck().then(setHealth).catch(() => setHealth({ status: 'unreachable' }))
    const id = setInterval(() => {
      healthCheck().then(setHealth).catch(() => setHealth({ status: 'unreachable' }))
    }, 15_000)
    return () => clearInterval(id)
  }, [])

  // Rolling chart update
  useEffect(() => {
    const id = setInterval(() => {
      const now = new Date()
      const t   = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
      setThetaSeries  (p => [...p.slice(-29), { t, v: 0.6 + Math.random() * 0.35 }])
      setRequestSeries(p => [...p.slice(-29), { t, v: 2800 + Math.random() * 2000 }])
      setBotRateSeries(p => [...p.slice(-29), { t, v: Math.max(0.01, 0.07 + (Math.random() - 0.5) * 0.06) }])
    }, 5_000)
    return () => clearInterval(id)
  }, [])

  // Inject live alerts when anomaly fires
  useEffect(() => {
    if (!anomaly) return
    const newAlert = {
      sev: 'critical',
      msg: `Live anomaly — E_rec: ${anomaly.eRec?.toFixed(4)} — Trust: ${(anomaly.ts * 100).toFixed(1)}%`,
      site: user?.email ?? 'current-session',
      ts: new Date().toLocaleTimeString('en', { hour12: false }),
    }
    setAlerts(prev => [newAlert, ...prev.slice(0, 8)])
  }, [anomaly])

  // Bar chart data — requests by region
  const regionData = [
    { r: 'NA',  bots: 420,  human: 5200 },
    { r: 'EU',  bots: 380,  human: 4100 },
    { r: 'AS',  bots: 870,  human: 3600 },
    { r: 'SA',  bots: 210,  human: 980 },
    { r: 'AF',  bots: 190,  human: 720 },
    { r: 'ME',  bots: 150,  human: 560 },
    { r: 'OC',  bots: 62,   human: 420 },
  ]

  return (
    <div className={styles.layout}>
      <Sidebar active="admin" />

      <main className={styles.main}>
        {/* Anomaly banner */}
        {anomaly && (
          <div className={styles.anomalyBanner}>
            <span>⚠ LIVE IDENTITY ANOMALY — CURRENT SESSION</span>
            <span>E_rec: {anomaly.eRec?.toFixed(4)} · Trust: {(anomaly.ts * 100).toFixed(1)}%</span>
          </div>
        )}

        {/* Top bar */}
        <div className={styles.topBar}>
          <div>
            <div className={styles.pageTitle}>ADMIN OVERVIEW</div>
            <div className={styles.pageSub}>
              {new Date().toUTCString()} · {user?.id}
            </div>
          </div>
          <div className={styles.statusPill}>
            <div className={styles.statusDot}
              style={{ background: health?.status === 'ok' ? 'var(--accent3)' : 'var(--danger)',
                       animation: 'pulse 2s infinite' }} />
            <span>SYSTEM {health?.status?.toUpperCase() ?? '...'}</span>
            {health?.rl_steps !== undefined && (
              <span className={styles.statusMeta}>RL_STEPS: {health.rl_steps.toLocaleString()}</span>
            )}
          </div>
        </div>

        {/* KPI row */}
        <div className={styles.kpiGrid}>
          <KpiCard icon="⬡" label="ACTIVE SITES"     value="7"
            sub="3 enterprise · 4 standard" delta={2}
            color="var(--accent)" sparkData={genSeries(12, 6, 2)} />
          <KpiCard icon="◉" label="TOTAL USERS"      value="24,819"
            sub="↑ 312 this hour" delta={1.4}
            color="var(--accent3)" sparkData={genSeries(12, 24000, 600)} />
          <KpiCard icon="⚡" label="REQUESTS / MIN"   value="4,214"
            sub="peak: 6,890" delta={-3.2}
            color="var(--accent)" sparkData={requestSeries.slice(-12)} />
          <KpiCard icon="⚠" label="THREATS BLOCKED"  value="1,038"
            sub="last 60 min" delta={18}
            color="var(--danger)" sparkData={genSeries(12, 900, 300)} />
          <KpiCard icon="θ" label="AVG θ HUMANITY"   value="76.4%"
            sub="↑ from 74.1% yesterday" delta={-1}
            color="#00ffa3" sparkData={thetaSeries.slice(-12).map(d => ({ v: d.v * 100 }))} />
          <KpiCard icon="🤖" label="BOT RATE"         value="8.7%"
            sub="shadow-routed: 100%" delta={5}
            color="var(--warn)" sparkData={botRateSeries.slice(-12).map(d => ({ v: d.v * 100 }))} />
        </div>

        {/* Security health rings */}
        <div className={styles.secHealthCard}>
          <div className={styles.sectionTitle}>SECURITY HEALTH MATRIX</div>
          <div className={styles.ringsRow}>
            <HealthRing score={secScores.overall}    label="OVERALL"    size={96} />
            <div className={styles.ringsDivider} />
            <HealthRing score={secScores.biological} label="BIO GW"     size={76} />
            <HealthRing score={secScores.governor}   label="GOVERNOR"   size={76} />
            <HealthRing score={secScores.deception}  label="DECEPTION"  size={76} />
            <HealthRing score={secScores.watchdog}   label="WATCHDOG"   size={76} />
            <div className={styles.ringsDivider} />
            {/* Phase text breakdown */}
            <div className={styles.phaseBreakdown}>
              {[
                { n: 1, label: 'Biological Gateway',  score: secScores.biological, ok: true  },
                { n: 2, label: 'Resource Governor',   score: secScores.governor,   ok: true  },
                { n: 3, label: 'Offensive Deception', score: secScores.deception,  ok: true  },
                { n: 4, label: 'Session Watchdog',    score: secScores.watchdog,   ok: secScores.watchdog > 90 },
              ].map(ph => (
                <div key={ph.n} className={styles.phaseRow2}>
                  <span className={styles.phaseN}>PH{ph.n}</span>
                  <div className={styles.phaseMiniBar}>
                    <div style={{
                      height: '100%', borderRadius: 2,
                      width: ph.score + '%',
                      background: ph.score > 95 ? '#00ffa3' : ph.score > 80 ? 'var(--accent)' : 'var(--warn)',
                      transition: 'width 1s ease'
                    }} />
                  </div>
                  <span className={styles.phaseScore}
                    style={{ color: ph.score > 95 ? '#00ffa3' : ph.score > 80 ? 'var(--accent)' : 'var(--warn)' }}>
                    {ph.score}%
                  </span>
                  <span className={styles.phaseLabel}>{ph.label}</span>
                  <span className={styles.phaseStatus} style={{ color: ph.ok ? '#00ffa3' : '#ff3b5c' }}>
                    {ph.ok ? '● NOMINAL' : '● DEGRADED'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Threat Map */}
        <div className={styles.threatMapCard}>
          <div className={styles.sectionTitle}>LIVE GLOBAL THREAT MAP — PHASE 3 INTELLIGENCE</div>
          <ThreatMap height={320} maxArcs={14} />
        </div>

        {/* Chart row */}
        <div className={styles.chartGrid}>
          {/* Avg θ over time */}
          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>AVG θ HUMANITY — 30 MIN WINDOW</div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={thetaSeries}>
                <defs>
                  <linearGradient id="theta-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="var(--accent3)" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="var(--accent3)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="t" tick={{ fill: 'var(--text3)', fontSize: 8, fontFamily: 'var(--mono)' }} interval={5} />
                <YAxis domain={[0, 1]} tick={{ fill: 'var(--text3)', fontSize: 8, fontFamily: 'var(--mono)' }} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', fontFamily: 'var(--mono)', fontSize: 10 }} />
                <Area type="monotone" dataKey="v" stroke="var(--accent3)"
                  fill="url(#theta-grad)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Requests / min */}
          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>REQUEST VOLUME / MIN</div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={requestSeries}>
                <defs>
                  <linearGradient id="req-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="var(--accent)" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="t" tick={{ fill: 'var(--text3)', fontSize: 8, fontFamily: 'var(--mono)' }} interval={5} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 8, fontFamily: 'var(--mono)' }} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', fontFamily: 'var(--mono)', fontSize: 10 }} />
                <Area type="monotone" dataKey="v" stroke="var(--accent)"
                  fill="url(#req-grad)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Region traffic split */}
          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>TRAFFIC BY REGION — BOTS vs HUMANS</div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={regionData} barSize={14}>
                <XAxis dataKey="r" tick={{ fill: 'var(--text3)', fontSize: 9, fontFamily: 'var(--mono)' }} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 8, fontFamily: 'var(--mono)' }} />
                <Tooltip contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', fontFamily: 'var(--mono)', fontSize: 10 }} />
                <Bar dataKey="human" fill="var(--accent)"  fillOpacity={0.5} isAnimationActive={false} />
                <Bar dataKey="bots"  fill="var(--danger)"  fillOpacity={0.6} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Alert feed */}
        <div className={styles.alertCard}>
          <div className={styles.alertHeader}>
            <div className={styles.sectionTitle}>LIVE SECURITY ALERTS</div>
            <div className={styles.alertBadge}>{alerts.length} events</div>
          </div>
          <div className={styles.alertList}>
            {alerts.map((a, i) => (
              <AlertRow key={i} {...a} />
            ))}
          </div>
        </div>

        {/* Onboarding checklist */}
        <div className={styles.onboardCard}>
          <div className={styles.sectionTitle}>OPERATOR ONBOARDING CHECKLIST</div>
          <div className={styles.onboardGrid}>
            {[
              { done: true,  step: '01', label: 'Install SDK snippet',         desc: 'Embed entropy.js in your login page' },
              { done: true,  step: '02', label: 'Verify API key',              desc: 'Confirm token handshake with backend' },
              { done: true,  step: '03', label: 'Enable biometric capture',    desc: 'Keyboard + pointer collectors active' },
              { done: true,  step: '04', label: 'Configure shadow sandbox',    desc: 'Phase 3 MAB agent initialized' },
              { done: false, step: '05', label: 'Set re-auth thresholds',      desc: 'Tune drift sensitivity per user tier' },
              { done: false, step: '06', label: 'Connect SIEM webhook',        desc: 'Push alerts to Splunk / Datadog / PD' },
            ].map(item => (
              <div key={item.step} className={styles.onboardItem}
                style={{ opacity: item.done ? 1 : 0.55 }}>
                <div className={styles.onboardCheck}
                  style={{ borderColor: item.done ? 'var(--accent3)' : 'var(--border)',
                           background:   item.done ? 'rgba(0,255,163,.1)' : 'transparent' }}>
                  {item.done && <span style={{ color: 'var(--accent3)', fontSize: 11 }}>✓</span>}
                </div>
                <div>
                  <span className={styles.onboardStep}>{item.step}</span>
                  <span className={styles.onboardLabel}>{item.label}</span>
                  <div className={styles.onboardDesc}>{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}