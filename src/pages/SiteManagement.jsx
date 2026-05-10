import { useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import styles from './SiteManagement.module.css'

// ── Sidebar (shared pattern) ───────────────────────────────────────────────
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
            <div className={styles.sideLogoSub}>SITE MANAGEMENT</div>
          </div>
        </div>
        <div className={styles.trustMeter}>
          <div className={styles.trustLabel}>SESSION TRUST</div>
          <div className={styles.trustBar}>
            <div className={styles.trustFill} style={{ width: (trustScore * 100) + '%', background: trustColor }} />
          </div>
          <div className={styles.trustVal} style={{ color: trustColor }}>{(trustScore * 100).toFixed(1)}%</div>
        </div>
        <nav className={styles.nav}>
          {[
            { id: 'admin',         label: 'ADMIN OVERVIEW', icon: '⬡', path: '/admin' },
            { id: 'profile-build', label: 'PROFILE BUILD',  icon: '◈', path: '/profile-build' },
            { id: 'dashboard',     label: 'DASHBOARD',      icon: '◈', path: '/dashboard' },
            { id: 'threats',       label: 'THREAT INTEL',   icon: '◉', path: '/threats' },
            { id: 'sites',         label: 'SITE MGMT',      icon: '◫', path: '/sites' },
          ].map(item => (
            <button key={item.id}
              className={`${styles.navItem} ${active === item.id ? styles.navActive : ''}`}
              onClick={() => navigate(item.path)}>
              <span className={styles.navIcon}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
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

// ── Site health badge ──────────────────────────────────────────────────────
function HealthBadge({ score }) {
  const color = score >= 90 ? '#00ffa3' : score >= 70 ? '#ffb800' : '#ff3b5c'
  const label = score >= 90 ? 'HEALTHY' : score >= 70 ? 'WARN' : 'CRITICAL'
  return (
    <span className={styles.healthBadge} style={{ color, borderColor: color, background: `${color}12` }}>
      <span className={styles.healthDot} style={{ background: color, animation: 'pulse 2s infinite' }} />
      {label}
    </span>
  )
}

// ── API Key row ────────────────────────────────────────────────────────────
function ApiKeyRow({ keyData, onRevoke, onCopy }) {
  const [revealed, setRevealed] = useState(false)
  const masked = keyData.key.slice(0, 8) + '••••••••••••••••••••' + keyData.key.slice(-4)

  return (
    <div className={styles.keyRow} style={{ opacity: keyData.revoked ? 0.4 : 1 }}>
      <div className={styles.keyMeta}>
        <span className={styles.keyName}>{keyData.name}</span>
        <span className={styles.keyEnv}
          style={{ color: keyData.env === 'production' ? 'var(--accent3)' : 'var(--warn)' }}>
          {keyData.env.toUpperCase()}
        </span>
        {keyData.revoked && <span className={styles.keyRevoked}>REVOKED</span>}
      </div>
      <div className={styles.keyValue}>
        <code className={styles.keyCode}>{revealed ? keyData.key : masked}</code>
      </div>
      <div className={styles.keyStats}>
        <span>Created: <b>{keyData.created}</b></span>
        <span>Last used: <b>{keyData.lastUsed}</b></span>
        <span>Calls: <b>{keyData.calls.toLocaleString()}</b></span>
      </div>
      <div className={styles.keyActions}>
        <button className={styles.keyBtn} onClick={() => setRevealed(r => !r)}
          disabled={keyData.revoked}>
          {revealed ? 'HIDE' : 'REVEAL'}
        </button>
        <button className={styles.keyBtn} onClick={() => onCopy(keyData.key)}
          disabled={keyData.revoked}>
          COPY
        </button>
        <button className={styles.keyBtnDanger} onClick={() => onRevoke(keyData.id)}
          disabled={keyData.revoked}>
          {keyData.revoked ? 'REVOKED' : 'REVOKE'}
        </button>
      </div>
    </div>
  )
}

// ── Policy slider row ─────────────────────────────────────────────────────
function PolicySlider({ label, desc, value, min, max, step, unit, onChange, color = 'var(--accent)' }) {
  return (
    <div className={styles.policySlider}>
      <div className={styles.policySliderTop}>
        <div>
          <span className={styles.policySliderLabel}>{label}</span>
          <span className={styles.policySliderDesc}>{desc}</span>
        </div>
        <div className={styles.policySliderVal} style={{ color }}>
          {value}{unit}
        </div>
      </div>
      <div className={styles.sliderTrack}>
        <div className={styles.sliderFill}
          style={{ width: ((value - min) / (max - min) * 100) + '%', background: color }} />
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(+e.target.value)}
          className={styles.sliderInput}
        />
      </div>
    </div>
  )
}

// ── Toggle switch ─────────────────────────────────────────────────────────
function Toggle({ label, desc, value, onChange }) {
  return (
    <div className={styles.toggleRow}>
      <div className={styles.toggleInfo}>
        <span className={styles.toggleLabel}>{label}</span>
        <span className={styles.toggleDesc}>{desc}</span>
      </div>
      <button
        className={styles.toggleBtn}
        onClick={() => onChange(!value)}
        style={{
          background: value ? 'rgba(0,255,163,.15)' : 'var(--bg3)',
          borderColor: value ? 'var(--accent3)' : 'var(--border)',
        }}
      >
        <div className={styles.toggleKnob}
          style={{ transform: value ? 'translateX(18px)' : 'translateX(0)',
                   background: value ? 'var(--accent3)' : 'var(--text3)' }} />
      </button>
    </div>
  )
}

// ── Initial state ─────────────────────────────────────────────────────────
const INITIAL_SITES = [
  {
    id: 'site-001', name: 'api.acme.io',    plan: 'Enterprise', health: 96,
    requests: 284_000, blocked: 12_400, users: 8_400,
    created: '2024-01-12',
  },
  {
    id: 'site-002', name: 'auth.stripe.io', plan: 'Enterprise', health: 91,
    requests: 192_000, blocked: 9_800, users: 5_200,
    created: '2024-02-28',
  },
  {
    id: 'site-003', name: 'login.shopify',  plan: 'Standard',   health: 88,
    requests: 98_000, blocked: 6_200, users: 2_100,
    created: '2024-03-15',
  },
  {
    id: 'site-004', name: 'admin.vercel',   plan: 'Standard',   health: 73,
    requests: 44_000, blocked: 3_800, users: 900,
    created: '2024-04-02',
  },
]

const INITIAL_KEYS = [
  {
    id: 'k1', name: 'Production Key',   env: 'production', revoked: false,
    key: 'ep_live_8f2a9b4c1e7d3f6a2b8c9d4e1f7a3b5c',
    created: '2024-01-12', lastUsed: 'just now', calls: 284_128,
  },
  {
    id: 'k2', name: 'Staging Key',      env: 'staging',    revoked: false,
    key: 'ep_test_3a1b2c4d5e6f7a8b9c0d1e2f3a4b5c6d',
    created: '2024-02-05', lastUsed: '2h ago', calls: 14_200,
  },
  {
    id: 'k3', name: 'CI/CD Key',        env: 'staging',    revoked: false,
    key: 'ep_test_9z8y7x6w5v4u3t2s1r0q9p8o7n6m5l4',
    created: '2024-03-20', lastUsed: '1d ago', calls: 2_800,
  },
  {
    id: 'k4', name: 'Legacy Key',       env: 'production', revoked: true,
    key: 'ep_live_1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p',
    created: '2023-11-01', lastUsed: '45d ago', calls: 98_444,
  },
]

const DEFAULT_POLICY = {
  thetaThreshold:    0.3,
  eRecThreshold:     0.18,
  driftThreshold:    2.0,
  reauthCooldown:    30,
  shadowBotTheta:    0.1,
  argonMaxMemory:    65536,
  sessionTTL:        24,
  minSamples:        50,
  enableShadow:      true,
  enableWatchdog:    true,
  enableFeatureSel:  true,
  enableHoneypot:    true,
  enablePassiveReauth: true,
  blockOnCritical:   false,
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function SiteManagement() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [sites,        setSites]       = useState(INITIAL_SITES)
  const [keys,         setKeys]        = useState(INITIAL_KEYS)
  const [policy,       setPolicy]      = useState(DEFAULT_POLICY)
  const [selectedSite, setSelectedSite]= useState(INITIAL_SITES[0].id)
  const [tab,          setTab]         = useState('overview') // overview | keys | policy | webhook
  const [toast,        setToast]       = useState(null)
  const [newKeyName,   setNewKeyName]  = useState('')
  const [newKeyEnv,    setNewKeyEnv]   = useState('staging')
  const [generating,   setGenerating]  = useState(false)
  const [savedPolicy,  setSavedPolicy] = useState(false)
  const [webhookUrl,   setWebhookUrl]  = useState('')
  const [webhookEvents,setWebhookEvents]=useState(['anomaly', 'shadow_route', 'reauth'])

  const site = sites.find(s => s.id === selectedSite)

  const showToast = useCallback((msg, color = 'var(--accent3)') => {
    setToast({ msg, color })
    setTimeout(() => setToast(null), 2800)
  }, [])

  const handleCopy = useCallback(key => {
    navigator.clipboard.writeText(key).then(() => showToast('API key copied to clipboard'))
  }, [showToast])

  const handleRevoke = useCallback(id => {
    setKeys(prev => prev.map(k => k.id === id ? { ...k, revoked: true } : k))
    showToast('Key revoked successfully', 'var(--warn)')
  }, [showToast])

  const handleGenerate = useCallback(() => {
    if (!newKeyName.trim()) return
    setGenerating(true)
    setTimeout(() => {
      const chars = 'abcdef0123456789'
      const rand32 = () => Array.from({ length: 32 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
      const prefix = newKeyEnv === 'production' ? 'ep_live_' : 'ep_test_'
      const newKey = {
        id:       'k' + Date.now(),
        name:     newKeyName.trim(),
        env:      newKeyEnv,
        revoked:  false,
        key:      prefix + rand32(),
        created:  new Date().toISOString().split('T')[0],
        lastUsed: 'never',
        calls:    0,
      }
      setKeys(prev => [newKey, ...prev])
      setNewKeyName('')
      setGenerating(false)
      showToast('New API key generated', 'var(--accent3)')
    }, 900)
  }, [newKeyName, newKeyEnv, showToast])

  const handleSavePolicy = useCallback(() => {
    setSavedPolicy(true)
    showToast('Policy saved and applied', 'var(--accent3)')
    setTimeout(() => setSavedPolicy(false), 2000)
  }, [showToast])

  const updatePolicy = useCallback((key, val) => {
    setPolicy(prev => ({ ...prev, [key]: val }))
  }, [])

  const WEBHOOK_EVENTS = ['anomaly', 'shadow_route', 'reauth', 'force_logout', 'bot_blocked', 'drift_spike']

  return (
    <div className={styles.layout}>
      <Sidebar active="sites" />

      <main className={styles.main}>
        {/* Toast */}
        {toast && (
          <div className={styles.toast} style={{ borderColor: toast.color, color: toast.color }}>
            ✓ {toast.msg}
          </div>
        )}

        {/* Header */}
        <div className={styles.topBar}>
          <div>
            <div className={styles.pageTitle}>SITE MANAGEMENT</div>
            <div className={styles.pageSub}>{sites.length} sites · API keys · Policy configuration</div>
          </div>
          <button className={styles.newSiteBtn}>+ ONBOARD SITE</button>
        </div>

        <div className={styles.body}>
          {/* Site list */}
          <div className={styles.siteList}>
            <div className={styles.siteListTitle}>MONITORED SITES</div>
            {sites.map(s => (
              <div key={s.id}
                className={`${styles.siteItem} ${selectedSite === s.id ? styles.siteItemActive : ''}`}
                onClick={() => setSelectedSite(s.id)}>
                <div className={styles.siteName}>{s.name}</div>
                <div className={styles.siteMeta}>
                  <span className={styles.sitePlan}
                    style={{ color: s.plan === 'Enterprise' ? 'var(--accent)' : 'var(--text3)' }}>
                    {s.plan.toUpperCase()}
                  </span>
                  <HealthBadge score={s.health} />
                </div>
                <div className={styles.siteStats}>
                  <span>{(s.requests / 1000).toFixed(0)}k req</span>
                  <span>{(s.blocked / 1000).toFixed(1)}k blocked</span>
                </div>
              </div>
            ))}

            {/* Add site placeholder */}
            <div className={styles.siteItemAdd}>
              <span>+ ADD SITE</span>
            </div>
          </div>

          {/* Detail panel */}
          {site && (
            <div className={styles.detail}>
              {/* Site header */}
              <div className={styles.detailHeader}>
                <div>
                  <div className={styles.detailSiteName}>{site.name}</div>
                  <div className={styles.detailMeta}>
                    ID: {site.id} · Since {site.created} · {site.plan} Plan
                  </div>
                </div>
                <HealthBadge score={site.health} />
              </div>

              {/* Quick stats */}
              <div className={styles.quickStats}>
                {[
                  { label: 'TOTAL REQUESTS', val: site.requests.toLocaleString(), color: 'var(--accent)' },
                  { label: 'BLOCKED',        val: site.blocked.toLocaleString(),  color: 'var(--danger)' },
                  { label: 'ACTIVE USERS',   val: site.users.toLocaleString(),    color: 'var(--accent3)' },
                  { label: 'BLOCK RATE',     val: ((site.blocked / site.requests) * 100).toFixed(1) + '%', color: 'var(--warn)' },
                ].map(s => (
                  <div key={s.label} className={styles.quickStat}>
                    <div className={styles.quickStatVal} style={{ color: s.color }}>{s.val}</div>
                    <div className={styles.quickStatLabel}>{s.label}</div>
                  </div>
                ))}
              </div>

              {/* Tab bar */}
              <div className={styles.tabBar}>
                {[
                  { id: 'overview', label: 'OVERVIEW'  },
                  { id: 'keys',     label: 'API KEYS'  },
                  { id: 'policy',   label: 'POLICY'    },
                  { id: 'webhook',  label: 'WEBHOOKS'  },
                ].map(t => (
                  <button key={t.id}
                    className={`${styles.tab} ${tab === t.id ? styles.tabActive : ''}`}
                    onClick={() => setTab(t.id)}>
                    {t.label}
                  </button>
                ))}
              </div>

              {/* ── OVERVIEW TAB ── */}
              {tab === 'overview' && (
                <div className={styles.tabContent}>
                  <div className={styles.overviewGrid}>
                    {/* Phase status */}
                    <div className={styles.overviewCard}>
                      <div className={styles.overviewCardTitle}>PIPELINE STATUS</div>
                      {[
                        { n: 1, label: 'Biological Gateway',  ok: true,  note: '1D-CNN v2.3 · 8-channel' },
                        { n: 2, label: 'Resource Governor',   ok: true,  note: 'DQN active · ε=0.12' },
                        { n: 3, label: 'Offensive Deception', ok: true,  note: 'MAB arm 2 · 14 bots routed' },
                        { n: 4, label: 'Session Watchdog',    ok: policy.enableWatchdog, note: 'PPO · 30s heartbeat' },
                      ].map(ph => (
                        <div key={ph.n} className={styles.phRow}>
                          <div className={styles.phNum}>PH{ph.n}</div>
                          <div className={styles.phDot}
                            style={{ background: ph.ok ? 'var(--accent3)' : 'var(--text3)',
                                     animation:  ph.ok ? 'pulse 2s infinite' : 'none' }} />
                          <div>
                            <div className={styles.phLabel}>{ph.label}</div>
                            <div className={styles.phNote}>{ph.note}</div>
                          </div>
                          <div className={styles.phStatus}
                            style={{ color: ph.ok ? 'var(--accent3)' : 'var(--text3)' }}>
                            {ph.ok ? 'ACTIVE' : 'OFF'}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Traffic breakdown */}
                    <div className={styles.overviewCard}>
                      <div className={styles.overviewCardTitle}>TRAFFIC BREAKDOWN</div>
                      {[
                        { label: 'Human users',       val: site.requests - site.blocked, color: 'var(--accent3)', pct: (1 - site.blocked / site.requests) * 100 },
                        { label: 'Bots blocked',       val: Math.floor(site.blocked * 0.6), color: 'var(--danger)', pct: 6 },
                        { label: 'Shadow-routed bots', val: Math.floor(site.blocked * 0.4), color: 'var(--warn)',   pct: 4 },
                      ].map(r => (
                        <div key={r.label} className={styles.trafficRow}>
                          <span className={styles.trafficLabel}>{r.label}</span>
                          <div className={styles.trafficBar}>
                            <div style={{ height: '100%', width: r.pct + '%', background: r.color, borderRadius: 2 }} />
                          </div>
                          <span className={styles.trafficVal} style={{ color: r.color }}>
                            {r.val.toLocaleString()}
                          </span>
                        </div>
                      ))}
                    </div>

                    {/* SDK integration snippet */}
                    <div className={styles.overviewCard} style={{ gridColumn: '1 / -1' }}>
                      <div className={styles.overviewCardTitle}>SDK INTEGRATION SNIPPET</div>
                      <pre className={styles.codeBlock}>{`<!-- Add to your login page <head> -->
<script
  src="https://cdn.entropy.prime/sdk/v1/entropy.js"
  data-api-key="${keys.find(k => !k.revoked && k.env === 'production')?.key?.slice(0, 20) ?? 'ep_live_••••••••••••'}••••"
  data-auto-init
  defer
></script>

<!-- Optional: configure policy overrides per-site -->
<script>
  window.EntropyConfig = {
    thetaThreshold: ${policy.thetaThreshold},
    shadowMode:     ${policy.enableShadow},
    sessionTTL:     ${policy.sessionTTL}  // hours
  }
</script>`}</pre>
                    </div>
                  </div>
                </div>
              )}

              {/* ── API KEYS TAB ── */}
              {tab === 'keys' && (
                <div className={styles.tabContent}>
                  {/* Generate key form */}
                  <div className={styles.genKeyCard}>
                    <div className={styles.overviewCardTitle}>GENERATE NEW KEY</div>
                    <div className={styles.genKeyRow}>
                      <input
                        className={styles.genKeyInput}
                        placeholder="Key name (e.g. Prod Backend)"
                        value={newKeyName}
                        onChange={e => setNewKeyName(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleGenerate()}
                      />
                      <select className={styles.genKeySelect}
                        value={newKeyEnv} onChange={e => setNewKeyEnv(e.target.value)}>
                        <option value="production">PRODUCTION</option>
                        <option value="staging">STAGING</option>
                      </select>
                      <button className={styles.genKeyBtn}
                        onClick={handleGenerate}
                        disabled={generating || !newKeyName.trim()}>
                        {generating ? '⟳ GENERATING...' : '+ GENERATE KEY'}
                      </button>
                    </div>
                    <div className={styles.genKeyWarning}>
                      ⚠ Production keys provide live biometric scoring. Staging keys use a test model with reduced accuracy.
                    </div>
                  </div>

                  {/* Key list */}
                  <div className={styles.keyList}>
                    {keys.map(k => (
                      <ApiKeyRow key={k.id} keyData={k} onRevoke={handleRevoke} onCopy={handleCopy} />
                    ))}
                  </div>

                  {/* Key usage note */}
                  <div className={styles.keyNote}>
                    <div className={styles.keyNoteTitle}>AUTHENTICATION FLOW</div>
                    <div className={styles.keyNoteText}>
                      Each API key authenticates your backend with Entropy Prime. Include it as{' '}
                      <code>X-API-Key: ep_live_...</code> on server-to-server calls, or embed it
                      in the SDK snippet for browser-side biometric capture. Keys are scoped per-site
                      and cannot be used across sites. Revoked keys are immediately rejected.
                    </div>
                  </div>
                </div>
              )}

              {/* ── POLICY TAB ── */}
              {tab === 'policy' && (
                <div className={styles.tabContent}>
                  <div className={styles.policyGrid}>
                    {/* Thresholds */}
                    <div className={styles.policyCard}>
                      <div className={styles.overviewCardTitle}>DETECTION THRESHOLDS</div>
                      <PolicySlider
                        label="θ Bot Threshold"
                        desc="Requests below this θ are classified as bots"
                        value={policy.thetaThreshold} min={0.05} max={0.6} step={0.01} unit=""
                        onChange={v => updatePolicy('thetaThreshold', v)}
                        color="var(--accent)"
                      />
                      <PolicySlider
                        label="E_rec Anomaly Threshold"
                        desc="Autoencoder error triggering identity anomaly"
                        value={policy.eRecThreshold} min={0.05} max={0.5} step={0.01} unit=""
                        onChange={v => updatePolicy('eRecThreshold', v)}
                        color="var(--warn)"
                      />
                      <PolicySlider
                        label="Behavioral Drift Threshold"
                        desc="σ-normalized drift triggering re-auth"
                        value={policy.driftThreshold} min={0.5} max={6} step={0.1} unit="σ"
                        onChange={v => updatePolicy('driftThreshold', v)}
                        color="var(--danger)"
                      />
                      <PolicySlider
                        label="Shadow-Route θ Cutoff"
                        desc="Ultra-low θ users routed to honeypot"
                        value={policy.shadowBotTheta} min={0.01} max={0.25} step={0.01} unit=""
                        onChange={v => updatePolicy('shadowBotTheta', v)}
                        color="#a78bfa"
                      />
                    </div>

                    {/* Session settings */}
                    <div className={styles.policyCard}>
                      <div className={styles.overviewCardTitle}>SESSION SETTINGS</div>
                      <PolicySlider
                        label="Session TTL"
                        desc="Hours before session requires full re-auth"
                        value={policy.sessionTTL} min={1} max={72} step={1} unit="h"
                        onChange={v => updatePolicy('sessionTTL', v)}
                        color="var(--accent3)"
                      />
                      <PolicySlider
                        label="Min Profile Samples"
                        desc="Keystrokes before drift detection activates"
                        value={policy.minSamples} min={10} max={200} step={5} unit=""
                        onChange={v => updatePolicy('minSamples', v)}
                        color="var(--accent)"
                      />
                      <PolicySlider
                        label="Re-auth Cooldown"
                        desc="Minutes between consecutive re-auth prompts"
                        value={policy.reauthCooldown} min={5} max={120} step={5} unit="m"
                        onChange={v => updatePolicy('reauthCooldown', v)}
                        color="var(--accent)"
                      />
                      <PolicySlider
                        label="Argon2 Max Memory"
                        desc="Peak memory (KB) for DQN 'punisher' preset"
                        value={policy.argonMaxMemory} min={16384} max={262144} step={8192} unit="KB"
                        onChange={v => updatePolicy('argonMaxMemory', v)}
                        color="var(--warn)"
                      />
                    </div>

                    {/* Feature toggles */}
                    <div className={styles.policyCard}>
                      <div className={styles.overviewCardTitle}>FEATURE TOGGLES</div>
                      <Toggle label="Shadow Sandbox"         desc="Route ultra-low θ bots to honeypot instead of blocking"
                        value={policy.enableShadow}       onChange={v => updatePolicy('enableShadow', v)} />
                      <Toggle label="Session Watchdog"       desc="PPO-based continuous identity verification"
                        value={policy.enableWatchdog}     onChange={v => updatePolicy('enableWatchdog', v)} />
                      <Toggle label="Per-User Feature Sel."  desc="Adaptive Welford feature selection per user ID"
                        value={policy.enableFeatureSel}   onChange={v => updatePolicy('enableFeatureSel', v)} />
                      <Toggle label="Honeypot Harvesting"    desc="Collect automation signatures for threat intelligence"
                        value={policy.enableHoneypot}     onChange={v => updatePolicy('enableHoneypot', v)} />
                      <Toggle label="Passive Re-auth"        desc="Invisible re-auth prompts via behavioral challenge"
                        value={policy.enablePassiveReauth} onChange={v => updatePolicy('enablePassiveReauth', v)} />
                      <Toggle label="Block on Critical"      desc="Hard-block (HTTP 403) critical bot traffic"
                        value={policy.blockOnCritical}    onChange={v => updatePolicy('blockOnCritical', v)} />
                    </div>
                  </div>

                  <button className={styles.savePolicyBtn}
                    onClick={handleSavePolicy}
                    style={{ background: savedPolicy ? 'var(--accent3)' : 'var(--accent)',
                             color: 'var(--bg)' }}>
                    {savedPolicy ? '✓ POLICY SAVED' : 'SAVE & APPLY POLICY'}
                  </button>
                </div>
              )}

              {/* ── WEBHOOK TAB ── */}
              {tab === 'webhook' && (
                <div className={styles.tabContent}>
                  <div className={styles.webhookCard}>
                    <div className={styles.overviewCardTitle}>WEBHOOK ENDPOINT</div>
                    <div className={styles.webhookRow}>
                      <div className={styles.webhookMethod}>POST</div>
                      <input
                        className={styles.webhookInput}
                        placeholder="https://your-backend.io/entropy-webhook"
                        value={webhookUrl}
                        onChange={e => setWebhookUrl(e.target.value)}
                      />
                      <button className={styles.webhookSaveBtn}
                        onClick={() => showToast('Webhook saved — test ping sent')}>
                        SAVE
                      </button>
                    </div>

                    <div className={styles.overviewCardTitle} style={{ marginTop: 20 }}>TRIGGER EVENTS</div>
                    <div className={styles.webhookEvents}>
                      {WEBHOOK_EVENTS.map(evt => (
                        <button key={evt}
                          className={styles.evtChip}
                          onClick={() => setWebhookEvents(prev =>
                            prev.includes(evt) ? prev.filter(e => e !== evt) : [...prev, evt]
                          )}
                          style={{
                            borderColor: webhookEvents.includes(evt) ? 'var(--accent3)' : 'var(--border)',
                            color:       webhookEvents.includes(evt) ? 'var(--accent3)' : 'var(--text3)',
                            background:  webhookEvents.includes(evt) ? 'rgba(0,255,163,.08)' : 'transparent',
                          }}>
                          {evt}
                        </button>
                      ))}
                    </div>

                    <div className={styles.overviewCardTitle} style={{ marginTop: 20 }}>EXAMPLE PAYLOAD</div>
                    <pre className={styles.codeBlock}>{`{
  "event":       "anomaly",
  "site_id":     "${site.id}",
  "user_id":     "uid_8821",
  "timestamp":   1718019241,
  "e_rec":       0.2312,
  "trust_score": 0.61,
  "drift":       2.87,
  "action":      "passive_reauth",
  "metadata": {
    "theta":     0.42,
    "phase":     4,
    "ip_hash":   "sha256:a1b2c3..."
  }
}`}</pre>

                    <div className={styles.webhookNote}>
                      Webhook requests include an <code>X-Entropy-Signature</code> header (HMAC-SHA256).
                      Verify it using your site secret to prevent spoofing. Max 3 retries with
                      exponential backoff. Delivery timeout: 5s.
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}