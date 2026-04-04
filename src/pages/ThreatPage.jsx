import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getHoneypotSignatures } from '../services/api'
import styles from './ThreatPage.module.css'

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
        <div className={styles.trustMeter}>
          <div className={styles.trustLabel}>SESSION TRUST</div>
          <div className={styles.trustBar}>
            <div className={styles.trustFill} style={{ width: (trustScore * 100) + '%', background: trustColor }} />
          </div>
          <div className={styles.trustVal} style={{ color: trustColor }}>{(trustScore * 100).toFixed(1)}%</div>
        </div>
        <nav className={styles.nav}>
          {[
            { id: 'dashboard', label: 'DASHBOARD',   icon: '◈', path: '/dashboard' },
            { id: 'threats',   label: 'THREAT INTEL',icon: '◉', path: '/threats' },
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

export default function ThreatPage() {
  const [sigs,     setSigs]     = useState([])
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState(null)
  const [error,    setError]    = useState(null)

  const fetchSigs = async () => {
    setLoading(true)
    try {
      const data = await getHoneypotSignatures()
      setSigs(data.signatures || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSigs()
    const id = setInterval(fetchSigs, 10_000)
    return () => clearInterval(id)
  }, [])

  const thetaColor = t => t < 0.1 ? '#ff3b5c' : t < 0.3 ? '#ffb800' : '#00ffa3'

  return (
    <div className={styles.layout}>
      <Sidebar active="threats" />
      <main className={styles.main}>
        <div className={styles.topBar}>
          <div>
            <div className={styles.pageTitle}>THREAT INTELLIGENCE</div>
            <div className={styles.pageSub}>Phase 3 — Honeypot Signature Harvest</div>
          </div>
          <button className={styles.refreshBtn} onClick={fetchSigs}>↺ REFRESH</button>
        </div>

        {/* Summary cards */}
        <div className={styles.summaryRow}>
          <div className={styles.summaryCard}>
            <div className={styles.summaryVal} style={{ color: 'var(--danger)' }}>{sigs.length}</div>
            <div className={styles.summaryLabel}>BOT SIGNATURES HARVESTED</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryVal} style={{ color: 'var(--warn)' }}>
              {sigs.filter(s => s.theta < 0.1).length}
            </div>
            <div className={styles.summaryLabel}>HIGH-CONFIDENCE BOTS (θ &lt; 0.1)</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryVal} style={{ color: 'var(--accent)' }}>
              {new Set(sigs.map(s => s.ua || 'unknown')).size}
            </div>
            <div className={styles.summaryLabel}>DISTINCT USER AGENTS</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryVal} style={{ color: 'var(--accent3)' }}>
              {sigs.length > 0
                ? (sigs.reduce((s, x) => s + x.theta, 0) / sigs.length * 100).toFixed(1) + '%'
                : '—'}
            </div>
            <div className={styles.summaryLabel}>AVG θ SCORE</div>
          </div>
        </div>

        {error && (
          <div className={styles.errorBox}>
            BACKEND UNREACHABLE — {error} — run <code>uvicorn backend.main:app</code>
          </div>
        )}

        {/* Signatures table */}
        <div className={styles.tableCard}>
          <div className={styles.tableHeader}>
            <span>TIMESTAMP</span>
            <span>θ SCORE</span>
            <span>USER AGENT</span>
            <span>PATH</span>
            <span>STATUS</span>
          </div>

          {loading && !sigs.length && (
            <div className={styles.empty}>
              <div className={styles.spinner} />
              <span>Polling honeypot engine...</span>
            </div>
          )}

          {!loading && !sigs.length && !error && (
            <div className={styles.empty}>
              <span style={{ color: 'var(--text3)' }}>No bot signatures captured yet.</span>
              <span style={{ color: 'var(--text3)', fontSize: 11 }}>
                Bots with θ &lt; 0.1 will appear here after being shadow-routed.
              </span>
            </div>
          )}

          {sigs.map((sig, i) => (
            <div key={i}
              className={`${styles.tableRow} ${selected === i ? styles.rowSelected : ''}`}
              onClick={() => setSelected(selected === i ? null : i)}>
              <span className={styles.mono}>{new Date(sig.ts * 1000).toLocaleTimeString()}</span>
              <span style={{ color: thetaColor(sig.theta), fontFamily: 'var(--mono)', fontSize: 12 }}>
                {(sig.theta * 100).toFixed(1)}%
              </span>
              <span className={styles.ua}>{sig.ua || 'unknown'}</span>
              <span className={styles.mono}>{sig.path || '/'}</span>
              <span className={styles.badge} style={{
                background: 'rgba(255,59,92,.1)', color: 'var(--danger)',
                border: '1px solid rgba(255,59,92,.2)'
              }}>SHADOW</span>
            </div>
          ))}
        </div>

        {/* Detail panel */}
        {selected !== null && sigs[selected] && (
          <div className={styles.detailPanel}>
            <div className={styles.detailTitle}>SIGNATURE DETAIL — #{selected}</div>
            <pre className={styles.detailPre}>
              {JSON.stringify(sigs[selected], null, 2)}
            </pre>
          </div>
        )}

        {/* Info box */}
        <div className={styles.infoBox}>
          <div className={styles.infoTitle}>HOW PHASE 3 WORKS</div>
          <div className={styles.infoText}>
            When θ &lt; 0.1 (high-confidence bot), Entropy Prime returns HTTP 200 with a synthetic session token
            instead of blocking. The bot is silently routed to a shadow sandbox via ASGI middleware.
            Every subsequent request from the bot serves fake data (users, transactions, API keys)
            while harvesting its automation signature for threat intelligence.
          </div>
        </div>
      </main>
    </div>
  )
}
