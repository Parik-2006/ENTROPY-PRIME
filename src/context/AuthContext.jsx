/**
 * AuthContext.jsx  v2.0.0
 *
 * Changes from v1.0.0
 * ────────────────────
 * • `onboardingState` is now a first-class piece of auth context, driven by
 *   the value returned by the login and sync endpoints.  Every consumer can
 *   read it without making extra API calls.
 *
 * • `isProfileStable` derived boolean exposed so route guards and components
 *   have a single, consistent flag rather than computing it inline from
 *   profileStats.sampleCount.
 *
 * • Watchdog heartbeat now passes `onboarding_state` to /session/verify so
 *   the server can apply its own drift gate without trusting the client's
 *   sample count claim.
 *
 * • Drift re-auth logic respects the onboarding gate: anomalies received
 *   while the profile is still `collecting` or `syncing` are logged but do
 *   NOT trigger force-logout on the client side (matching the server-side
 *   behaviour in session_verify).
 *
 * • `resetProfile()` action added — calls POST /biometric/profile/reset and
 *   drops local state back to the collecting baseline so ProfileBuildPage
 *   can restart.
 *
 * • Session restoration now fetches the onboarding state from /me so the
 *   router can redirect to /profile-build when appropriate without an extra
 *   round-trip.
 *
 * • No changes to the biometrics engine initialisation or heartbeat timing.
 */

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from 'react'
import { EntropyPrimeClient } from '../services/biometrics'
import {
  sendWatchdogHeartbeat, logoutUser, fetchMe, resetBiometricProfile,
  registerAuthErrorHandler,
} from '../services/api'

const AuthCtx = createContext(null)

// ── Onboarding state constants (mirrors backend/database.py) ─────────────────
export const ONBOARDING_COLLECTING = 'collecting'
export const ONBOARDING_SYNCING    = 'syncing'
export const ONBOARDING_STABLE     = 'stable'
export const ONBOARDING_DRIFTED    = 'drifted'


export function AuthProvider({ children }) {
  const [user,            setUser]            = useState(null)
  const [loading,         setLoading]         = useState(true)
  const [epReady,         setEpReady]         = useState(false)
  const [liveTheta,       setLiveTheta]       = useState(null)
  const [trustScore,      setTrustScore]      = useState(1.0)
  const [anomaly,         setAnomaly]         = useState(null)
  const [sigCount,        setSigCount]        = useState(0)
  const [profileStats,    setProfileStats]    = useState(null)
  const [liveDrift,       setLiveDrift]       = useState(0)
  const [selectedFeatures,setSelectedFeatures]= useState([])
  // Frozen-template identity diagnostics (dev debug panel + trust signal)
  const [identity,        setIdentity]        = useState(null)

  /**
   * onboardingState is the canonical profile state machine value.
   * Consumers should read this rather than deriving from profileStats.sampleCount.
   *
   *   collecting  → profile-build page; progress bar shown
   *   syncing     → profile-build page; "saving…" indicator
   *   stable      → dashboard accessible; drift detection armed
   *   drifted     → profile-build page with reset prompt
   */
  const [onboardingState, setOnboardingState] = useState(ONBOARDING_COLLECTING)

  const clientRef = useRef(null)
  // True once session restoration has finished. Gates the heartbeat so it can
  // never run against an unvalidated / dead token during app boot (race fix).
  const [authReady, setAuthReady] = useState(false)
  // Guards the clean-logout path so concurrent 401s only log out once.
  const sessionExpiredRef = useRef(false)

  // Derived convenience flag
  const isProfileStable = onboardingState === ONBOARDING_STABLE

  // ── Clean logout on an invalid/expired session (no infinite 401 loop) ───────
  const handleSessionExpired = useCallback((reason = 'expired') => {
    if (sessionExpiredRef.current) return        // idempotent
    sessionExpiredRef.current = true
    console.warn(`[SESSION] Session invalid/expired (${reason}) → clean logout`)
    try { clientRef.current?.destroy?.() } catch { /* noop */ }
    localStorage.removeItem('ep_token')
    localStorage.removeItem('ep_user')
    setUser(null)                                // PrivateRoute → redirect to /login
    setAnomaly(null)
    setIdentity(null)
    setTrustScore(1.0)
    setOnboardingState(ONBOARDING_COLLECTING)
  }, [])

  // Any authenticated API call that 401s routes here (registered once below).
  useEffect(() => {
    registerAuthErrorHandler((path, msg) => {
      console.warn(`[AUTH] 401 on ${path}: ${msg}`)
      handleSessionExpired('api_401')
    })
  }, [handleSessionExpired])

  // ── Session restoration ───────────────────────────────────────────────────
  // On refresh we MUST validate the stored token with the server BEFORE marking
  // the user as authenticated. Previously the user was set first and a /me 401
  // was swallowed, leaving the app "logged in" with a dead session — which then
  // looped 401s on the heartbeat and EnrollPage sync. Now: validate, then either
  // restore (200) or clean-logout (401).
  useEffect(() => {
    const restoreUser = async () => {
      const storedUser  = localStorage.getItem('ep_user')
      const storedToken = localStorage.getItem('ep_token')
      console.log('[TOKEN] Restore:', storedToken ? `present (…${storedToken.slice(-8)})` : 'none')

      if (!storedToken || !storedUser) {
        setLoading(false); setAuthReady(true)
        return
      }

      let parsedUser
      try { parsedUser = JSON.parse(storedUser) } catch {
        console.warn('[SESSION] Corrupt stored user → clearing')
        localStorage.removeItem('ep_user'); localStorage.removeItem('ep_token')
        setLoading(false); setAuthReady(true)
        return
      }

      try {
        // Authoritative check: does the session still exist on the server?
        const me = await fetchMe(storedToken)
        console.log('[SESSION] Restored & validated for', parsedUser.email ?? parsedUser.id)
        setUser(parsedUser)
        setOnboardingState(me.onboarding_state ?? ONBOARDING_COLLECTING)
        setTrustScore(me.trust_score ?? 1.0)
        sessionExpiredRef.current = false
      } catch (err) {
        if (err?.status === 401) {
          // Token is genuinely invalid/expired (e.g. session wiped by a backend
          // restart, or 30-min TTL elapsed). Clean logout — do NOT set the user,
          // so the router redirects to /login instead of booting a dead session.
          console.warn('[SESSION] Stored token rejected (401) → clean logout, redirect to /login')
          localStorage.removeItem('ep_token')
          localStorage.removeItem('ep_user')
          // user stays null → PrivateRoute redirects to /login
        } else {
          // Transient (backend unreachable / network). Keep the user optimistically
          // so a momentary blip doesn't force a re-login; the heartbeat re-checks.
          console.warn('[SESSION] /me check failed (non-401, transient):', err?.message)
          setUser(parsedUser)
        }
      } finally {
        setLoading(false)
        setAuthReady(true)
      }
    }
    restoreUser()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Boot biometrics engine ─────────────────────────────────────────────────
  useEffect(() => {
    const ep = new EntropyPrimeClient()
    clientRef.current = ep

    ep.setUpdateCallback((payload) => {
      const {
        type, theta, eRec, trustScore: ts,
        drift, selectedFeatures: sf, featureNames,
      } = payload
      if (type === 'ready') setEpReady(true)
      if (type === 'score') {
        setLiveTheta(theta)
        if (drift !== undefined) setLiveDrift(drift)
        if (sf) setSelectedFeatures(featureNames || [])
      }
      if (type === 'anomaly') {
        setTrustScore(ts)
        setAnomaly({ eRec, ts, drift, time: Date.now() })
      }
      // Frozen-template identity score — the dominant human-vs-human signal.
      // Drives trustScore (which ceilings the visible confidence in
      // TrustContext, so a different human is pulled into the re-auth zone).
      if (type === 'identity') {
        setTrustScore(ts)
        setIdentity({
          score:        payload.identityScore,
          raw:          payload.rawScore,
          suspicion:    payload.suspicion,
          zone:         payload.zone,
          reauth:       payload.reauth,
          corroborated: payload.corroborated,
          driftCount:   payload.driftCount,
          typingSim:    payload.typingSim,
          digraphSim:   payload.digraphSim,
          mouseSim:     payload.mouseSim,
          // enhanced keyboard-biometric signals
          digraphProfileSim: payload.digraphProfileSim,
          trigraphSim:       payload.trigraphSim,
          burstSim:          payload.burstSim,
          backspaceSim:      payload.backspaceSim,
          spacebarSim:       payload.spacebarSim,
          dwellSim:          payload.dwellSim,
          phraseSim:         payload.phraseSim,
          gated:        payload.gated,
          t:            Date.now(),
        })
      }
    })

    ep.init().catch(console.error)
    return () => ep.destroy()
  }, [])

  // ── Restore per-user biometric profile after login ─────────────────────────
  useEffect(() => {
    if (user && clientRef.current) {
      clientRef.current.setUser(user.id)
    }
  }, [user])

  // ── Live profile stats polling (for progress bar) ─────────────────────────
  useEffect(() => {
    if (!user) return
    const id = setInterval(() => {
      try {
        const ep = clientRef.current
        if (!ep) return
        const pStats = ep.getProfileStats()
        setProfileStats(pStats)
      } catch (e) {
        console.error('Failed to update profile stats:', e)
      }
    }, 2000)
    return () => clearInterval(id)
  }, [user])

  // ── Watchdog heartbeat every 30 s ─────────────────────────────────────────
  // Race fix: never run before session restoration has completed and validated
  // the token (authReady), and never with no user.
  useEffect(() => {
    if (!user || !authReady) return
    const id = setInterval(async () => {
      if (sessionExpiredRef.current) return      // session already gone — stop
      try {
        const ep = clientRef.current
        if (!ep) return

        const { eRec, trustScore: ts, idle } = await ep.checkIdentity()
        const vec    = await ep.getLatentVector()
        const pStats = ep.getProfileStats()

        setProfileStats(pStats)
        setTrustScore(ts)

        // Pass the authoritative onboarding state to the server so it can
        // gate drift detection independently of the sample-count claim.
        // Phase D.1 (shadow): include the current normalized feature window so the
        // backend can log a server-side comparison. Optional + best-effort; the
        // heartbeat behaves identically if this is null.
        let featureWindow = null
        try { featureWindow = ep.getFeatureVector?.() ?? null } catch { featureWindow = null }

        const res = await sendWatchdogHeartbeat({
          userId:            user.id,
          latentVector:      vec,
          eRec,
          trustScore:        ts,
          behavioralDrift:   pStats?.lastDrift ?? 0,
          adaptiveThreshold: pStats?.adaptiveThreshold ?? 1.8,
          selectedFeatures:  pStats?.selectedFeatures ?? [],
          sampleCount:       pStats?.sampleCount ?? 0,
          onboarding_state:  onboardingState,
          featureWindow,
        })

        // Update our local state from the server's authoritative response.
        if (res.onboarding_state) {
          setOnboardingState(res.onboarding_state)
        }

        // Only trigger re-auth prompts when the profile is stable AND the
        // session is active. Idle periods carry no new behavioural evidence,
        // so they must never escalate to a deviation / re-auth prompt.
        if (!idle && (res.action === 'passive_reauth' || res.action === 'force_logout')) {
          if (isProfileStable) {
            setAnomaly({ type: 'reauth', ...res })
          } else {
            console.info(
              '[AuthContext] Watchdog anomaly suppressed (profile not stable):',
              res.action, onboardingState,
            )
          }
        }
      } catch (err) {
        // A 401 here means the session expired/was wiped mid-session. Clean up
        // ONCE instead of logging a 401 every 30 s forever.
        if (err?.status === 401 || /expired session|invalid or expired/i.test(err?.message || '')) {
          console.warn('[HEARTBEAT] Session no longer valid → stopping heartbeat, logging out')
          handleSessionExpired('heartbeat_401')
        } else {
          console.error('[HEARTBEAT] Failed (non-auth, transient):', err?.message || err)
        }
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [user, authReady, onboardingState, isProfileStable, handleSessionExpired])

  // ── Actions ───────────────────────────────────────────────────────────────

  const login = useCallback((userData, token, serverOnboardingState) => {
    console.log('[TOKEN] Saved on login (…%s)', String(token).slice(-8))
    console.log('[AUTH] Login → authenticated:', userData?.email ?? userData?.id)
    sessionExpiredRef.current = false            // clear any prior expired state
    setAuthReady(true)
    localStorage.setItem('ep_token', token)
    localStorage.setItem('ep_user',  JSON.stringify(userData))
    setUser(userData)
    setTrustScore(1.0)
    setAnomaly(null)
    setSigCount(c => c + 1)
    // Use the state returned by the login endpoint; fall back to collecting
    // so new users always land on the profile-build page first.
    setOnboardingState(serverOnboardingState ?? ONBOARDING_COLLECTING)
    if (clientRef.current) {
      clientRef.current.setUser(userData.id)
    }
  }, [])

  const logout = useCallback(() => {
    if (clientRef.current) {
      clientRef.current._persistProfile?.()
    }
    const token = localStorage.getItem('ep_token')
    if (token) {
      logoutUser(token).catch(console.error)
    }
    localStorage.removeItem('ep_token')
    localStorage.removeItem('ep_user')
    setUser(null)
    setTrustScore(1.0)
    setAnomaly(null)
    setProfileStats(null)
    setSelectedFeatures([])
    setOnboardingState(ONBOARDING_COLLECTING)
    setLiveDrift(0)
  }, [])

  /**
   * resetProfile — called after re-auth to wipe the drifted EMA baseline.
   * The server wipes the MongoDB document and returns `collecting`; we mirror
   * that locally so the ProfileBuildPage re-renders in collection mode.
   */
  const resetProfile = useCallback(async (reason = 'user_request') => {
    const token = localStorage.getItem('ep_token')
    if (!token) return

    try {
      await resetBiometricProfile(token, reason)
    } catch (err) {
      console.error('[AuthContext] Profile reset failed:', err)
    }

    // Reset client-side engine state regardless of API result
    if (clientRef.current) {
      clientRef.current.resetProfile?.()
      clientRef.current.resetEnrollmentTemplate?.()
    }
    setIdentity(null)
    setOnboardingState(ONBOARDING_COLLECTING)
    setProfileStats(null)
    setLiveDrift(0)
    setAnomaly(null)
  }, [])

  /**
   * confirmStable — called by ProfileBuildPage when the sync endpoint
   * returns `stable` to promote the local state without waiting for the
   * next heartbeat cycle.
   */
  const confirmStable = useCallback(() => {
    setOnboardingState(ONBOARDING_STABLE)
  }, [])

  const getClient = useCallback(() => clientRef.current, [])

  const restoreSession = useCallback(async () => {
    setLoading(true)
    try {
      const storedToken = localStorage.getItem('ep_token')
      const storedUser  = localStorage.getItem('ep_user')
      if (storedToken && storedUser) {
        setUser(JSON.parse(storedUser))
        try {
          const me = await fetchMe(storedToken)
          setOnboardingState(me.onboarding_state ?? ONBOARDING_COLLECTING)
        } catch {
          /* non-fatal */
        }
      }
    } catch {
      logout()
    } finally {
      setLoading(false)
    }
  }, [logout])

  // Dev helper: discard the frozen template so the next sufficient typist
  // re-enrolls (used by the identity debug panel during testing).
  const reEnroll = useCallback(() => {
    clientRef.current?.resetEnrollmentTemplate?.()
    setIdentity(null)
    setTrustScore(1.0)
  }, [])

  // FIX 1 + FIX 4 — called after a successful re-authentication / verify.
  // Resets the engine (trust=1.0, identityScore=100, streak=0, watchdog
  // penalties cleared) and starts the cooldown, then clears local auth state so
  // the session returns to a clean trusted state without a logout.
  const confirmVerified = useCallback(() => {
    clientRef.current?.confirmVerified?.()
    setTrustScore(1.0)
    setAnomaly(null)
    setIdentity({
      score: 100, zone: 'trusted', reauth: false,
      typingSim: 1, digraphSim: 1, mouseSim: 1, gated: false, t: Date.now(),
    })
    console.log('[AuthContext] Reauth Success → Trust Reset → Cooldown Started')
  }, [])

  return (
    <AuthCtx.Provider value={{
      // Identity
      user, loading, login, logout, restoreSession,
      // Biometrics engine
      epReady, liveTheta, trustScore, anomaly, sigCount,
      profileStats, liveDrift, selectedFeatures,
      // Frozen-template identity scoring
      identity, reEnroll, confirmVerified,
      // Onboarding state machine
      onboardingState, isProfileStable,
      resetProfile, confirmStable,
      // Raw client access
      getClient,
    }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)