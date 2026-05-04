import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import styles from './DashboardPage.module.css'

/**
 * Sidebar navigation component
 */
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
            { id: 'profile-build', label: 'PROFILE BUILD', icon: '◈', path: '/profile-build' },
            { id: 'dashboard', label: 'DASHBOARD', icon: '◉', path: '/dashboard' },
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

/**
 * Post-login profile building & threat detection demo page.
 * User types normally to build their profile, then can deliberately
 * type abnormally or let someone else type to trigger re-auth.
 */
export default function ProfileBuildPage() {
  const navigate = useNavigate()
  const { user, logout, getClient, profileStats, liveDrift, anomaly } = useAuth()

  const [practiceText, setPracticeText] = useState('')
  const [isReauthRequired, setIsReauthRequired] = useState(false)
  const [driftHistory, setDriftHistory] = useState([])
  const [recentEvent, setRecentEvent] = useState(null)

  // Compute profile stability once at render time
  const isProfileStable = profileStats && profileStats.sampleCount >= 50
  const profileProgress = profileStats ? Math.min(profileStats.sampleCount / 50, 1) : 0

  // Debug profile stability
  console.log(`[ProfileBuildPage] profileStats.sampleCount=${profileStats?.sampleCount}, isProfileStable=${isProfileStable}`)

  // Redirect if no user
  useEffect(() => {
    if (!user) navigate('/login')
  }, [user, navigate])

  // Track drift in real-time and trigger re-auth if it spikes (only after profile is stable)
  useEffect(() => {
    const id = setInterval(() => {
      if (liveDrift !== null && liveDrift !== undefined) {
        setDriftHistory(prev => [...prev.slice(-99), { time: Date.now(), drift: liveDrift }])
        
        // Debug logging
        console.log(`[Drift Check] liveDrift=${liveDrift.toFixed(2)}, isProfileStable=${isProfileStable}, threshold=0.5`)
        
        // Only flag for re-auth AFTER profile is stable (50+ samples)
        // Before that, just show the drift value as informational
        if (isProfileStable && liveDrift > 0.5) {  // Even lower threshold for testing
          console.log(`🚨 TRIGGER RE-AUTH: Drift ${liveDrift.toFixed(2)} > 0.5`)
          setIsReauthRequired(true)
          setRecentEvent({
            type: 'anomaly',
            message: `⚠ ANOMALY DETECTED: Drift ${liveDrift.toFixed(2)} exceeds threshold (0.5)`,
            severity: 'critical'
          })
        }
      }
    }, 1000)
    return () => clearInterval(id)
  }, [liveDrift, isProfileStable])

  // Monitor for anomalies from context (only after profile is stable)
  useEffect(() => {
    if (anomaly && isProfileStable) {
      setIsReauthRequired(true)
      setRecentEvent({
        type: 'anomaly',
        message: `⚠ WATCHDOG ALERT: Behavioral mismatch detected`,
        severity: 'critical'
      })
    }
  }, [anomaly, isProfileStable])

  const handleReauth = useCallback(() => {
    logout()
    navigate('/login')
  }, [logout, navigate])

  const handleProceedToDashboard = useCallback(() => {
    if (profileStats?.sampleCount >= 50) {
      navigate('/dashboard')
    }
  }, [profileStats, navigate])

  return (
    <div className={styles.page}>
      <div className={styles.scanline} />
      
      {/* Sidebar */}
      <Sidebar active="profile-build" />

      {/* Left panel */}
      <div className={styles.left} style={{ padding: '40px', maxWidth: '400px' }}>
        <div className={styles.brand}>
          <div className={styles.logo}>EP</div>
          <div>
            <div className={styles.brandName}>PROFILE BUILD</div>
            <div className={styles.brandSub}>Establish your baseline typing pattern</div>
          </div>
        </div>

        <div style={{ marginTop: '40px' }}>
          <h3 style={{ color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: '12px', marginBottom: '16px' }}>
            USER: {user?.email}
          </h3>

          <div style={{ marginBottom: '32px' }}>
            <div style={{ color: 'var(--text2)', fontSize: '11px', marginBottom: '8px' }}>PROFILE PROGRESS</div>
            <div style={{
              height: '24px',
              background: 'var(--bg2)',
              border: '1px solid var(--border)',
              borderRadius: '2px',
              overflow: 'hidden'
            }}>
              <div style={{
                height: '100%',
                width: (profileProgress * 100) + '%',
                background: isProfileStable ? 'var(--accent3)' : 'var(--accent)',
                transition: 'width 0.3s ease'
              }} />
            </div>
            <div style={{
              color: isProfileStable ? 'var(--accent3)' : 'var(--text3)',
              fontSize: '11px',
              marginTop: '6px',
              fontWeight: 600
            }}>
              {profileStats?.sampleCount ?? 0} / 50 SAMPLES {isProfileStable ? '✓ STABLE' : ''}
            </div>
          </div>

          <div style={{ 
            padding: '16px',
            background: 'rgba(0,255,163,.05)',
            border: '1px solid rgba(0,255,163,.2)',
            borderRadius: '2px',
            marginBottom: '24px'
          }}>
            <div style={{ fontSize: '11px', color: 'var(--text2)', lineHeight: 1.6 }}>
              <strong>Instructions:</strong>
              <br />1. Type naturally in the text box to establish your baseline pattern
              <br />2. Reach 50+ samples to stabilize your profile
              <br />3. Then, deliberately type FAST or RANDOMLY to trigger re-auth
              <br />4. Or give your keyboard to a friend!
            </div>
          </div>

          {isReauthRequired && (
            <div style={{
              padding: '12px',
              background: 'rgba(255,59,92,.1)',
              border: '1px solid rgba(255,59,92,.3)',
              borderRadius: '2px',
              marginBottom: '24px'
            }}>
              <div style={{ fontSize: '11px', color: '#ff3b5c', fontWeight: 600, marginBottom: '8px' }}>
                🔐 RE-AUTHENTICATION REQUIRED
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text3)', marginBottom: '12px' }}>
                {recentEvent?.message}
              </div>
              <button onClick={handleReauth} style={{
                padding: '8px 12px',
                background: '#ff3b5c',
                color: 'white',
                border: 'none',
                borderRadius: '2px',
                fontSize: '10px',
                fontWeight: 600,
                cursor: 'pointer'
              }}>
                AUTHENTICATE AGAIN
              </button>
            </div>
          )}

          {isProfileStable && !isReauthRequired && (
            <button onClick={handleProceedToDashboard} style={{
              width: '100%',
              padding: '12px',
              background: 'var(--accent3)',
              color: 'var(--bg)',
              border: 'none',
              borderRadius: '2px',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
              marginTop: '24px'
            }}>
              PROCEED TO DASHBOARD →
            </button>
          )}
        </div>
      </div>

      {/* Right panel */}
      <div className={styles.right} style={{ padding: '40px' }}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span style={{ color: 'var(--accent)' }}>REAL-TIME TYPING ZONE</span>
          </div>

          {/* Live drift indicator */}
          <div style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '11px', color: 'var(--text2)' }}>BEHAVIORAL DRIFT</span>
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                color: liveDrift > 2 ? '#ff3b5c' : liveDrift > 1 ? '#ffb800' : '#00ffa3'
              }}>
                {liveDrift?.toFixed(2) ?? '0.00'}
              </span>
            </div>
            <div style={{
              height: '4px',
              background: 'var(--bg2)',
              borderRadius: '2px',
              overflow: 'hidden'
            }}>
              <div style={{
                height: '100%',
                width: Math.min(liveDrift / 3, 1) * 100 + '%',
                background: liveDrift > 2 ? '#ff3b5c' : liveDrift > 1 ? '#ffb800' : '#00ffa3',
                transition: 'width 0.2s ease'
              }} />
            </div>
            <div style={{ fontSize: '9px', color: 'var(--text3)', marginTop: '4px' }}>
              {liveDrift > 2 ? '🔴 ANOMALY' : liveDrift > 1 ? '🟡 WARNING' : '🟢 NORMAL'}
            </div>
          </div>

          {/* Practice text input */}
          <div style={{ marginBottom: '24px' }}>
            <label style={{ fontSize: '11px', color: 'var(--text2)', display: 'block', marginBottom: '8px' }}>
              TYPE HERE TO BUILD PROFILE
            </label>
            <textarea
              value={practiceText}
              onChange={(e) => setPracticeText(e.target.value)}
              onFocus={() => console.log('Textarea focused - keystrokes should be captured')}
              onBlur={() => console.log('Textarea blurred')}
              placeholder="Type naturally... or deliberately type FAST to trigger anomaly detection"
              style={{
                width: '100%',
                height: '120px',
                padding: '12px',
                background: 'var(--bg2)',
                border: '1px solid var(--border)',
                borderRadius: '2px',
                color: 'var(--text)',
                fontFamily: 'var(--mono)',
                fontSize: '12px',
                resize: 'none',
                boxSizing: 'border-box'
              }}
            />
          </div>

          {/* Drift history mini chart */}
          {driftHistory.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text2)', marginBottom: '12px' }}>DRIFT OVER TIME</div>
              <svg width="100%" height="60" style={{ border: '1px solid var(--border)' }}>
                <defs>
                  <linearGradient id="driftGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#00ffa3" stopOpacity="0.3" />
                    <stop offset="100%" stopColor="#00ffa3" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {/* Threshold line at 2.0 */}
                <line x1="0" y1="20" x2="100%" y2="20" stroke="rgba(255,59,92,.2)" strokeWidth="1" strokeDasharray="2,2" />
                
                {/* Plot drift values */}
                {driftHistory.map((point, i, arr) => {
                  const x = (i / Math.max(arr.length - 1, 1)) * 100
                  const y = 60 - Math.min(point.drift / 3, 1) * 60
                  return (
                    <circle key={i} cx={`${x}%`} cy={y} r="2"
                      fill={point.drift > 2 ? '#ff3b5c' : point.drift > 1 ? '#ffb800' : '#00ffa3'}
                    />
                  )
                })}
              </svg>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
