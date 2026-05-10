import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import styles from './DashboardPage.module.css'

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
            <div
              className={styles.trustFill}
              style={{ width: (trustScore * 100) + '%', background: trustColor }}
            />
          </div>
          <div className={styles.trustVal} style={{ color: trustColor }}>
            {(trustScore * 100).toFixed(1)}%
          </div>
        </div>

        <nav className={styles.nav}>
          {[
            { id: 'profile-build', label: 'PROFILE BUILD', icon: 'P', path: '/profile-build' },
            { id: 'dashboard', label: 'DASHBOARD', icon: 'D', path: '/dashboard' },
            { id: 'threats', label: 'THREAT INTEL', icon: 'T', path: '/threats' },
          ].map(item => (
            <button
              key={item.id}
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

export default function ProfileBuildPage() {
  const navigate = useNavigate()
  const { user, logout, profileStats, liveDrift, anomaly } = useAuth()

  const [practiceText, setPracticeText] = useState('')
  const [isReauthRequired, setIsReauthRequired] = useState(false)
  const [driftHistory, setDriftHistory] = useState([])
  const [recentEvent, setRecentEvent] = useState(null)

  const sampleCount = profileStats?.sampleCount ?? 0
  const isProfileStable = sampleCount >= 50
  const profileProgress = Math.min(sampleCount / 50, 1)
  const driftLevel = liveDrift > 2 ? 'ANOMALY' : liveDrift > 1 ? 'WARNING' : 'NORMAL'
  const driftColor = liveDrift > 2 ? '#ff3b5c' : liveDrift > 1 ? '#ffb800' : '#00ffa3'

  useEffect(() => {
    if (!user) navigate('/login')
  }, [user, navigate])

  useEffect(() => {
    const id = setInterval(() => {
      if (liveDrift !== null && liveDrift !== undefined) {
        setDriftHistory(prev => [...prev.slice(-99), { time: Date.now(), drift: liveDrift }])

        if (isProfileStable && liveDrift > 0.5) {
          setIsReauthRequired(true)
          setRecentEvent({
            type: 'anomaly',
            message: `Behavioral drift ${liveDrift.toFixed(2)} exceeded the re-authentication threshold.`,
            severity: 'critical',
          })
        }
      }
    }, 1000)

    return () => clearInterval(id)
  }, [liveDrift, isProfileStable])

  useEffect(() => {
    if (anomaly && isProfileStable) {
      setIsReauthRequired(true)
      setRecentEvent({
        type: 'anomaly',
        message: 'Watchdog detected a behavioral mismatch for this session.',
        severity: 'critical',
      })
    }
  }, [anomaly, isProfileStable])

  const handleReauth = useCallback(() => {
    logout()
    navigate('/login')
  }, [logout, navigate])

  const handleProceedToDashboard = useCallback(() => {
    if (isProfileStable && !isReauthRequired) {
      navigate('/dashboard')
    }
  }, [isProfileStable, isReauthRequired, navigate])

  return (
    <div className={styles.layout}>
      <div className={styles.scanline} />
      <Sidebar active="profile-build" />

      <main className={styles.main}>
        <div className={styles.topBar}>
          <div>
            <div className={styles.pageTitle}>PROFILE BUILD</div>
            <div className={styles.pageSub}>Continuous authentication baseline for {user?.email}</div>
          </div>
          <button
            className={styles.reauthBtn}
            onClick={handleProceedToDashboard}
            disabled={!isProfileStable || isReauthRequired}
          >
            OPEN DASHBOARD
          </button>
        </div>

        <div className={styles.profileStatusGrid}>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>P</div>
            <div className={styles.statVal} style={{ color: isProfileStable ? '#00ffa3' : 'var(--accent)' }}>
              {sampleCount}/50
            </div>
            <div className={styles.statLabel}>PROFILE SAMPLES</div>
            <div className={styles.statSub}>
              {isProfileStable ? 'Stable baseline ready' : `${50 - sampleCount} more needed`}
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>D</div>
            <div className={styles.statVal} style={{ color: driftColor }}>
              {liveDrift?.toFixed(2) ?? '0.00'}
            </div>
            <div className={styles.statLabel}>BEHAVIORAL DRIFT</div>
            <div className={styles.statSub}>{driftLevel}</div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>S</div>
            <div
              className={styles.statVal}
              style={{ color: isReauthRequired ? '#ff3b5c' : isProfileStable ? '#00ffa3' : 'var(--warn)' }}
            >
              {isReauthRequired ? 'LOCKED' : isProfileStable ? 'READY' : 'LEARNING'}
            </div>
            <div className={styles.statLabel}>WATCHDOG STATE</div>
            <div className={styles.statSub}>
              {isReauthRequired ? 'Re-authentication required' : isProfileStable ? 'Test scenarios enabled' : 'Collecting baseline'}
            </div>
          </div>
        </div>

        <div className={styles.profileGrid}>
          <section className={styles.profileWorkspace}>
            <div className={styles.chartTitle}>REAL-TIME TYPING ZONE</div>

            <div className={styles.profileProgressBlock}>
              <div className={styles.profileProgressMeta}>
                <span>PROFILE PROGRESS</span>
                <span>{Math.round(profileProgress * 100)}%</span>
              </div>
              <div className={styles.profileProgressTrackWide}>
                <div
                  className={styles.profileProgressFillWide}
                  style={{
                    width: (profileProgress * 100) + '%',
                    background: isProfileStable ? '#00ffa3' : 'var(--accent)',
                  }}
                />
              </div>
            </div>

            <label className={styles.profileInputLabel}>
              TYPE HERE TO BUILD AND TEST THE PROFILE
            </label>
            <textarea
              className={styles.profileTextarea}
              value={practiceText}
              onChange={(e) => setPracticeText(e.target.value)}
              placeholder="Type naturally for baseline. After 50 samples, type unusually fast or randomly to trigger anomaly detection."
            />

            <div className={styles.profileDriftPanel}>
              <div className={styles.profileProgressMeta}>
                <span>DRIFT OVER TIME</span>
                <span style={{ color: driftColor }}>{liveDrift?.toFixed(2) ?? '0.00'}</span>
              </div>
              <svg width="100%" height="96" className={styles.profileDriftChart}>
                <line x1="0" y1="32" x2="100%" y2="32" stroke="rgba(255,59,92,.25)" strokeWidth="1" strokeDasharray="3,3" />
                {driftHistory.map((point, i, arr) => {
                  const x = (i / Math.max(arr.length - 1, 1)) * 100
                  const y = 88 - Math.min(point.drift / 3, 1) * 78
                  return (
                    <circle
                      key={i}
                      cx={`${x}%`}
                      cy={y}
                      r="2.5"
                      fill={point.drift > 2 ? '#ff3b5c' : point.drift > 1 ? '#ffb800' : '#00ffa3'}
                    />
                  )
                })}
              </svg>
            </div>
          </section>

          <aside className={styles.profileGuide}>
            <div className={styles.chartTitle}>TEST SEQUENCE</div>
            <ol className={styles.profileSteps}>
              <li>Type naturally until the profile reaches 50 samples.</li>
              <li>Continue normal typing and confirm drift stays low.</li>
              <li>Type very fast, randomly, or let another person type.</li>
              <li>When drift crosses the threshold, re-authentication appears.</li>
            </ol>

            <div className={styles.profileGuideBox}>
              <div className={styles.accessTitle}>DEMO STATUS</div>
              <div className={styles.accessText}>
                {isReauthRequired
                  ? recentEvent?.message
                  : isProfileStable
                    ? 'Baseline is stable. You can now test abnormal behavior.'
                    : 'The system is still learning your normal cadence.'}
              </div>
            </div>
          </aside>
        </div>
      </main>

      {isReauthRequired && (
        <div className={styles.reauthOverlay} role="alertdialog" aria-modal="true">
          <div className={styles.reauthModal}>
            <div className={styles.reauthKicker}>SESSION WATCHDOG</div>
            <div className={styles.reauthTitle}>Re-authentication required</div>
            <div className={styles.reauthMessage}>
              {recentEvent?.message || 'Behavior no longer matches the saved profile.'}
            </div>
            <div className={styles.reauthMeta}>
              Drift: {liveDrift?.toFixed(2) ?? '0.00'} | Samples: {sampleCount}
            </div>
            <button className={styles.reauthPrimary} onClick={handleReauth}>
              AUTHENTICATE AGAIN
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
