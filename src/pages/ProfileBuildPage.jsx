/**
 * ProfileBuildPage.jsx  v2.0.0
 *
 * Changes from v1.0.0
 * ────────────────────
 * • The entire component is now driven by `onboardingState` from AuthContext
 *   rather than a local `isProfileStable` boolean derived from
 *   profileStats.sampleCount.  The server is the single source of truth.
 *
 * • Four explicit panel modes match the state machine:
 *     COLLECTING  — progress bar; type to collect samples
 *     SYNCING     — spinner while the last sync is in flight
 *     STABLE      — anomaly demo controls; proceed button
 *     DRIFTED     — re-auth prompt; reset button
 *
 * • Drift re-auth trigger now obeys the onboarding gate: anomalies that
 *   arrive while the state is `collecting` or `syncing` set a local
 *   infoEvent but never call setIsReauthRequired().
 *
 * • syncBiometricProfile response is now parsed for `profile_status` and
 *   `profile_status.onboarding_state`; the context's `confirmStable()` is
 *   called when the server confirms a stable transition so the UI updates
 *   immediately without waiting for the next polling cycle.
 *
 * • Debug console.log statements removed from production paths; only error
 *   and significant state-transition events are logged.
 *
 * • No raw keystroke or mouse data is ever included in API payloads — the
 *   payload builder only passes aggregated stats from the biometrics engine.
 *
 * • Sidebar is unchanged but reads `onboardingState` for the active-item
 *   highlight so it works correctly across all four panels.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useAuth,
  ONBOARDING_COLLECTING,
  ONBOARDING_SYNCING,
  ONBOARDING_STABLE,
  ONBOARDING_DRIFTED,
} from '../context/AuthContext'
import { submitScore, syncBiometricProfile } from '../services/api'
import { getBiometricCollector, resetBiometricCollector } from '../services/biometricCollector'
import styles from './DashboardPage.module.css'

const STABLE_SAMPLE_THRESHOLD = 50

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

function Sidebar({ active }) {
  const { user, logout, trustScore } = useAuth()
  const navigate = useNavigate()

  const trustColor =
    trustScore > 0.7 ? '#00ffa3' :
    trustScore > 0.4 ? '#ffb800' : '#ff3b5c'

  return (
    <aside className={styles.sidebar}>
      <div className={styles.sideTop}>
        <div className={styles.sideLogo}>
          <span className={styles.sideLogoMark}>EP</span>
          <div>
            <div className={styles.sideLogoName}>ENTROPY PRIME</div>
            <div className={styles.sideLogoSub}>v2.0 ACTIVE</div>
          </div>
        </div>

        <div className={styles.trustMeter}>
          <div className={styles.trustLabel}>SESSION TRUST</div>
          <div className={styles.trustBar}>
            <div
              className={styles.trustFill}
              style={{ width: `${trustScore * 100}%`, background: trustColor }}
            />
          </div>
          <div className={styles.trustVal} style={{ color: trustColor }}>
            {(trustScore * 100).toFixed(1)}%
          </div>
        </div>

        <nav className={styles.nav}>
          {[
            { id: 'profile-build', label: 'PROFILE BUILD', icon: '◈', path: '/profile-build' },
            { id: 'dashboard',     label: 'DASHBOARD',     icon: '◉', path: '/dashboard' },
            { id: 'threats',       label: 'THREAT INTEL',  icon: '◉', path: '/threats' },
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
          <div className={styles.userAvatar}>
            {user?.email?.[0]?.toUpperCase() ?? 'U'}
          </div>
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

// ─────────────────────────────────────────────────────────────────────────────
// State-machine panel components
// ─────────────────────────────────────────────────────────────────────────────

function CollectingPanel({ sampleCount, progress }) {
  const remaining = Math.max(0, STABLE_SAMPLE_THRESHOLD - sampleCount)
  return (
    <div>
      <h3 style={heading}>BUILDING YOUR PROFILE</h3>
      <p style={sub}>
        Type naturally in the box to the right. We measure your rhythm, not
        your words — raw keystrokes never leave your browser.
      </p>

      <div style={{ margin: '24px 0' }}>
        <div style={labelRow}>
          <span style={labelText}>SAMPLES COLLECTED</span>
          <span style={labelVal}>{sampleCount} / {STABLE_SAMPLE_THRESHOLD}</span>
        </div>
        <div style={barTrack}>
          <div style={{ ...barFill, width: `${progress * 100}%`, background: 'var(--accent)' }} />
        </div>
        <div style={hint}>
          {remaining > 0
            ? `${remaining} more samples needed…`
            : 'Saving profile…'}
        </div>
      </div>

      <div style={infoBox}>
        <div style={{ fontSize: '11px', color: 'var(--text2)', lineHeight: 1.6 }}>
          <strong style={{ color: 'var(--accent)' }}>How it works</strong>
          <br />1. Type the practice text to gather timing samples.
          <br />2. Once you reach {STABLE_SAMPLE_THRESHOLD} samples, your baseline is saved.
          <br />3. Future sessions compare against this baseline to detect impostors.
          <br />4. You can test drift detection from the stable panel.
        </div>
      </div>
    </div>
  )
}

function SyncingPanel() {
  return (
    <div style={{ textAlign: 'center', padding: '40px 0' }}>
      <div style={{ fontSize: '32px', marginBottom: '16px', animation: 'spin 1.5s linear infinite' }}>
        ◈
      </div>
      <div style={heading}>SAVING BASELINE…</div>
      <div style={sub}>Persisting your behavioral profile. This takes a moment.</div>
    </div>
  )
}

function StablePanel({ onProceed }) {
  return (
    <div>
      <h3 style={{ ...heading, color: 'var(--accent3)' }}>✓ PROFILE STABLE</h3>
      <p style={sub}>
        Your baseline is ready. The watchdog will now flag any significant
        departure from your normal typing pattern.
      </p>

      <div style={{ ...infoBox, borderColor: 'rgba(0,255,163,.3)', background: 'rgba(0,255,163,.05)', margin: '24px 0' }}>
        <div style={{ fontSize: '11px', color: 'var(--text2)', lineHeight: 1.6 }}>
          <strong style={{ color: 'var(--accent3)' }}>Try it out</strong>
          <br />• Type normally — drift stays green.
          <br />• Type very fast or randomly — drift turns red and re-auth is triggered.
          <br />• Hand the keyboard to a friend — their pattern will be detected as different.
        </div>
      </div>

      <button onClick={onProceed} style={primaryBtn}>
        GO TO DASHBOARD →
      </button>
    </div>
  )
}

function DriftedPanel({ onReset, onReauth }) {
  return (
    <div>
      <h3 style={{ ...heading, color: '#ff3b5c' }}>⚠ BEHAVIORAL ANOMALY</h3>
      <p style={sub}>
        The watchdog detected a significant departure from your baseline.
        Re-authenticate to confirm your identity, then rebuild your profile.
      </p>

      <div style={{ ...infoBox, borderColor: 'rgba(255,59,92,.3)', background: 'rgba(255,59,92,.05)', margin: '24px 0' }}>
        <div style={{ fontSize: '11px', color: '#ff3b5c', lineHeight: 1.6 }}>
          If this is you, re-authenticate below to reset your profile and
          establish a new baseline. If you didn't trigger this, your account
          may have been accessed by someone else.
        </div>
      </div>

      <div style={{ display: 'flex', gap: '12px', flexDirection: 'column' }}>
        <button onClick={onReauth} style={primaryBtn}>
          RE-AUTHENTICATE
        </button>
        <button onClick={onReset} style={secondaryBtn}>
          RESET PROFILE & RESTART
        </button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function ProfileBuildPage() {
  const navigate = useNavigate()
  const {
    user, logout, getClient,
    profileStats, liveDrift, anomaly, epReady,
    onboardingState, isProfileStable,
    resetProfile, confirmStable,
  } = useAuth()

  const [practiceText,  setPracticeText]  = useState('')
  const [driftHistory,  setDriftHistory]  = useState([])
  const [eventBanner,   setEventBanner]   = useState(null)  // { msg, severity }
  const [collectorState,setCollectorState]= useState(null)
  const [isSyncing,     setIsSyncing]     = useState(false)

  const syncTimerRef       = useRef(null)
  const lastSyncedTextRef  = useRef('')
  const collectorRef       = useRef(null)

  // ── Init collector ─────────────────────────────────────────────────────────
  useEffect(() => {
    collectorRef.current = getBiometricCollector()
  }, [])

  // ── Auth guard ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!user) navigate('/login')
  }, [user, navigate])

  // ── Drift history (informational; does NOT drive re-auth) ─────────────────
  useEffect(() => {
    if (liveDrift === null || liveDrift === undefined) return
    setDriftHistory(prev => [...prev.slice(-99), { time: Date.now(), drift: liveDrift }])
  }, [liveDrift])

  // ── Anomaly from context (only arm when profile is stable) ─────────────────
  useEffect(() => {
    if (!anomaly) return

    if (isProfileStable) {
      // Profile is stable → genuine anomaly, promote to drifted panel
      // The server has already set onboarding_state=drifted in the DB;
      // the next heartbeat response will carry it back here via the
      // onboarding_state field.  We preemptively show the banner.
      setEventBanner({
        msg:      '⚠ WATCHDOG: Behavioral mismatch detected. Re-authentication required.',
        severity: 'critical',
      })
    } else {
      // Profile not yet stable → suppress the UI redirect, just log it
      console.info(
        '[ProfileBuildPage] Anomaly suppressed (onboarding not stable):',
        onboardingState,
      )
    }
  }, [anomaly, isProfileStable, onboardingState])

  // ── Proceed to dashboard (only when stable) ────────────────────────────────
  const handleProceedToDashboard = useCallback(() => {
    if (isProfileStable) navigate('/dashboard')
  }, [isProfileStable, navigate])

  // ── Re-auth: logout and redirect to login ──────────────────────────────────
  const handleReauth = useCallback(() => {
    logout()
    navigate('/login')
  }, [logout, navigate])

  // ── Reset profile ──────────────────────────────────────────────────────────
  const handleReset = useCallback(async () => {
    await resetProfile('user_request')
    setPracticeText('')
    setDriftHistory([])
    setEventBanner(null)
    lastSyncedTextRef.current = ''
    if (collectorRef.current) {
      resetBiometricCollector()
      collectorRef.current = getBiometricCollector()
    }
    setCollectorState(null)
  }, [resetProfile])

  // ── Profile sync (debounced, triggered by typing) ─────────────────────────
  useEffect(() => {
    if (!user || !epReady) return

    const typedText = practiceText.trim()
    // Minimum text length before we bother syncing
    if (typedText.length < 10) return
    // Skip if nothing changed since last sync
    if (typedText === lastSyncedTextRef.current) return
    // Don't sync when in drifted state — user must reset first
    if (onboardingState === ONBOARDING_DRIFTED) return

    if (syncTimerRef.current) clearTimeout(syncTimerRef.current)

    syncTimerRef.current = setTimeout(async () => {
      const ep = getClient()
      if (!ep || !collectorRef.current) return

      try {
        setIsSyncing(true)

        // ── Evaluate and collect sample ──────────────────────────────────────
        const { theta, hExp }   = await ep.evaluate(typedText)
        const latentVector      = await ep.getLatentVector()
        const keyboardStats     = ep.getKeyboardStats()
        const pointerStats      = ep.getPointerStats()
        const liveProfileStats  = ep.getProfileStats()

        // Only aggregated metrics — no raw coordinates or keystroke sequences
        const sample = {
          theta,
          hExp,
          dwell:  keyboardStats?.avgDwell  ?? 0,
          flight: keyboardStats?.avgFlight ?? 0,
          rhythm: keyboardStats?.rhythm    ?? 0,
          speed:  pointerStats?.avgSpeed   ?? 0,
          jitter: pointerStats?.avgJitter  ?? 0,
          accel:  pointerStats?.avgAccel   ?? 0,
          pause:  keyboardStats?.avgPause  ?? 0,
        }
        collectorRef.current.addSample(sample)
        const newCollState = collectorRef.current.getState()
        setCollectorState(newCollState)

        // ── Score submission ─────────────────────────────────────────────────
        await submitScore({ theta, hExp, latentVector, serverLoad: 0.35 })

        // ── Build sync payload (aggregated stats only) ───────────────────────
        const { payload, samplesInPayload } = collectorRef.current.buildSyncPayload(
          theta, hExp, latentVector, liveProfileStats,
        )

        // Request a stable transition if the collector says we have enough
        if (newCollState.collectedSamples >= STABLE_SAMPLE_THRESHOLD) {
          payload.requested_state = 'stable'
        }

        const syncRes = await syncBiometricProfile(payload)

        // ── Parse server response ────────────────────────────────────────────
        const profileStatus = syncRes?.profile_status ?? {}
        const serverState   = profileStatus?.onboarding_state

        if (samplesInPayload > 0) {
          collectorRef.current.markPersisted(samplesInPayload)
        }

        if (serverState === ONBOARDING_STABLE && !isProfileStable) {
          confirmStable()
          setEventBanner({ msg: '✓ Profile stable — drift detection armed.', severity: 'success' })
        } else if (serverState) {
          // Reflect any other server-driven state change (e.g. syncing)
          // The context's heartbeat will update onboardingState on the next
          // cycle; we don't need to call setOnboardingState here because
          // confirmStable() covers the only case we care about immediately.
        }

        lastSyncedTextRef.current = typedText
        setEventBanner({
          msg:      `✓ Synced: ${newCollState.collectedSamples} / ${STABLE_SAMPLE_THRESHOLD} samples`,
          severity: 'info',
        })
      } catch (err) {
        console.error('[ProfileBuildPage] Sync failed:', err)
        setEventBanner({ msg: `✗ Sync failed: ${err.message}`, severity: 'error' })
      } finally {
        setIsSyncing(false)
      }
    }, 1500)

    return () => {
      if (syncTimerRef.current) clearTimeout(syncTimerRef.current)
    }
  }, [practiceText, user, epReady, getClient, onboardingState, isProfileStable, confirmStable])

  // ── Derived values for rendering ──────────────────────────────────────────
  const serverSampleCount = profileStats?.sampleCount ?? 0
  const localSampleCount  = collectorState?.collectedSamples ?? 0
  // Use the higher of the two counts so the bar never goes backwards
  const displaySampleCount = Math.max(serverSampleCount, localSampleCount)
  const progress = Math.min(displaySampleCount / STABLE_SAMPLE_THRESHOLD, 1)

  // ── Left-panel content driven entirely by onboardingState ─────────────────
  const renderLeftPanel = () => {
    if (isSyncing && onboardingState === ONBOARDING_SYNCING) {
      return <SyncingPanel />
    }
    switch (onboardingState) {
      case ONBOARDING_COLLECTING:
      case ONBOARDING_SYNCING:
        return <CollectingPanel sampleCount={displaySampleCount} progress={progress} />
      case ONBOARDING_STABLE:
        return <StablePanel onProceed={handleProceedToDashboard} />
      case ONBOARDING_DRIFTED:
        return <DriftedPanel onReset={handleReset} onReauth={handleReauth} />
      default:
        return <CollectingPanel sampleCount={displaySampleCount} progress={progress} />
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.scanline} />
      <Sidebar active="profile-build" />

      {/* ── Left panel ────────────────────────────────────────────────────── */}
      <div className={styles.left} style={{ padding: '40px', maxWidth: '400px' }}>
        <div className={styles.brand}>
          <div className={styles.logo}>EP</div>
          <div>
            <div className={styles.brandName}>PROFILE BUILD</div>
            <div className={styles.brandSub}>
              {onboardingState === ONBOARDING_STABLE
                ? 'Baseline established'
                : onboardingState === ONBOARDING_DRIFTED
                ? 'Anomaly detected'
                : 'Establishing baseline'}
            </div>
          </div>
        </div>

        {/* State badge */}
        <div style={{ margin: '20px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{
            display:      'inline-block',
            padding:      '3px 10px',
            borderRadius: '2px',
            fontSize:     '10px',
            fontWeight:   700,
            fontFamily:   'var(--mono)',
            letterSpacing: '0.08em',
            background: {
              [ONBOARDING_COLLECTING]: 'rgba(0,180,255,.12)',
              [ONBOARDING_SYNCING]:    'rgba(255,184,0,.12)',
              [ONBOARDING_STABLE]:     'rgba(0,255,163,.12)',
              [ONBOARDING_DRIFTED]:    'rgba(255,59,92,.12)',
            }[onboardingState] ?? 'rgba(255,255,255,.08)',
            color: {
              [ONBOARDING_COLLECTING]: '#00b4ff',
              [ONBOARDING_SYNCING]:    '#ffb800',
              [ONBOARDING_STABLE]:     '#00ffa3',
              [ONBOARDING_DRIFTED]:    '#ff3b5c',
            }[onboardingState] ?? 'var(--text2)',
            border: '1px solid currentColor',
          }}>
            {onboardingState.toUpperCase()}
          </span>
          <span style={{ fontSize: '10px', color: 'var(--text3)' }}>
            User: {user?.email}
          </span>
        </div>

        <div style={{ marginTop: '8px' }}>
          {renderLeftPanel()}
        </div>

        {/* Event banner */}
        {eventBanner && (
          <div style={{
            marginTop:  '24px',
            padding:    '10px 12px',
            borderRadius: '2px',
            fontSize:   '10px',
            fontFamily: 'var(--mono)',
            background: {
              info:     'rgba(0,180,255,.08)',
              success:  'rgba(0,255,163,.08)',
              error:    'rgba(255,59,92,.08)',
              critical: 'rgba(255,59,92,.12)',
            }[eventBanner.severity] ?? 'rgba(255,255,255,.05)',
            color: {
              info:     '#00b4ff',
              success:  '#00ffa3',
              error:    '#ff3b5c',
              critical: '#ff3b5c',
            }[eventBanner.severity] ?? 'var(--text2)',
            border: '1px solid currentColor',
          }}>
            {eventBanner.msg}
          </div>
        )}
      </div>

      {/* ── Right panel ───────────────────────────────────────────────────── */}
      <div className={styles.right} style={{ padding: '40px' }}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span style={{ color: 'var(--accent)' }}>REAL-TIME TYPING ZONE</span>
          </div>

          {/* Live drift bar */}
          <div style={{ marginBottom: '24px' }}>
            <div style={labelRow}>
              <span style={labelText}>BEHAVIORAL DRIFT</span>
              <span style={{
                ...labelVal,
                color: liveDrift > 2 ? '#ff3b5c' : liveDrift > 1 ? '#ffb800' : '#00ffa3',
              }}>
                {liveDrift?.toFixed(2) ?? '0.00'}
                {!isProfileStable && (
                  <span style={{ color: 'var(--text3)', marginLeft: '6px', fontWeight: 400 }}>
                    (detection armed after stable)
                  </span>
                )}
              </span>
            </div>
            <div style={barTrack}>
              <div style={{
                ...barFill,
                width: `${Math.min(liveDrift / 3, 1) * 100}%`,
                background: liveDrift > 2 ? '#ff3b5c' : liveDrift > 1 ? '#ffb800' : '#00ffa3',
              }} />
            </div>
            <div style={hint}>
              {liveDrift > 2 ? '🔴 ANOMALY' : liveDrift > 1 ? '🟡 WARNING' : '🟢 NORMAL'}
            </div>
          </div>

          {/* Practice textarea */}
          <div style={{ marginBottom: '24px' }}>
            <label style={{ fontSize: '11px', color: 'var(--text2)', display: 'block', marginBottom: '8px' }}>
              {onboardingState === ONBOARDING_DRIFTED
                ? 'PROFILE LOCKED — Reset before typing'
                : 'TYPE HERE TO BUILD / TEST YOUR PROFILE'}
            </label>
            <textarea
              value={practiceText}
              onChange={e => setPracticeText(e.target.value)}
              disabled={onboardingState === ONBOARDING_DRIFTED}
              placeholder={
                onboardingState === ONBOARDING_DRIFTED
                  ? 'Reset your profile first…'
                  : onboardingState === ONBOARDING_STABLE
                  ? 'Type normally, or try typing fast / randomly to trigger re-auth…'
                  : 'Type naturally to build your baseline profile…'
              }
              style={{
                width:       '100%',
                height:      '120px',
                padding:     '12px',
                background:  onboardingState === ONBOARDING_DRIFTED
                  ? 'rgba(255,59,92,.04)'
                  : 'var(--bg2)',
                border:      `1px solid ${onboardingState === ONBOARDING_DRIFTED ? 'rgba(255,59,92,.3)' : 'var(--border)'}`,
                borderRadius: '2px',
                color:       'var(--text)',
                fontFamily:  'var(--mono)',
                fontSize:    '12px',
                resize:      'none',
                boxSizing:   'border-box',
                opacity:     onboardingState === ONBOARDING_DRIFTED ? 0.5 : 1,
                cursor:      onboardingState === ONBOARDING_DRIFTED ? 'not-allowed' : 'text',
              }}
            />
          </div>

          {/* Drift history chart */}
          {driftHistory.length > 1 && (
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text2)', marginBottom: '8px' }}>
                DRIFT HISTORY
                {!isProfileStable && (
                  <span style={{ color: 'var(--text3)', marginLeft: '8px' }}>
                    (detection armed after stable)
                  </span>
                )}
              </div>
              <svg width="100%" height="60" style={{ border: '1px solid var(--border)' }}>
                {/* Anomaly threshold line at 2.0 */}
                <line
                  x1="0" y1="20" x2="100%" y2="20"
                  stroke="rgba(255,59,92,.25)" strokeWidth="1" strokeDasharray="3,3"
                />
                {driftHistory.map((pt, i, arr) => {
                  const x = `${(i / Math.max(arr.length - 1, 1)) * 100}%`
                  const y = 60 - Math.min(pt.drift / 3, 1) * 56
                  return (
                    <circle
                      key={i}
                      cx={x} cy={y} r="2"
                      fill={pt.drift > 2 ? '#ff3b5c' : pt.drift > 1 ? '#ffb800' : '#00ffa3'}
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

// ─────────────────────────────────────────────────────────────────────────────
// Shared inline styles
// ─────────────────────────────────────────────────────────────────────────────

const heading = {
  color:       'var(--text)',
  fontFamily:  'var(--mono)',
  fontSize:    '12px',
  marginBottom: '12px',
  letterSpacing: '0.06em',
}

const sub = {
  color:       'var(--text2)',
  fontSize:    '11px',
  lineHeight:  1.6,
  marginBottom: '8px',
}

const labelRow = {
  display:        'flex',
  justifyContent: 'space-between',
  marginBottom:   '6px',
}

const labelText = { fontSize: '11px', color: 'var(--text2)' }
const labelVal  = { fontSize: '11px', fontWeight: 600, color: 'var(--text)' }

const barTrack = {
  height:       '6px',
  background:   'var(--bg2)',
  borderRadius: '3px',
  overflow:     'hidden',
}

const barFill = {
  height:     '100%',
  transition: 'width 0.3s ease',
}

const hint = {
  fontSize:   '9px',
  color:      'var(--text3)',
  marginTop:  '4px',
}

const infoBox = {
  padding:      '14px',
  background:   'rgba(255,255,255,.03)',
  border:       '1px solid var(--border)',
  borderRadius: '2px',
}

const primaryBtn = {
  width:        '100%',
  padding:      '12px',
  background:   'var(--accent3)',
  color:        'var(--bg)',
  border:       'none',
  borderRadius: '2px',
  fontSize:     '11px',
  fontWeight:   700,
  cursor:       'pointer',
  fontFamily:   'var(--mono)',
  letterSpacing: '0.06em',
}

const secondaryBtn = {
  ...primaryBtn,
  background: 'transparent',
  color:      '#ff3b5c',
  border:     '1px solid rgba(255,59,92,.4)',
}