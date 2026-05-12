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
import { sendWatchdogHeartbeat, logoutUser, fetchMe, resetBiometricProfile } from '../services/api'

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

  // Derived convenience flag
  const isProfileStable = onboardingState === ONBOARDING_STABLE

  // ── Session restoration ───────────────────────────────────────────────────
  useEffect(() => {
    const restoreUser = async () => {
      try {
        const storedUser  = localStorage.getItem('ep_user')
        const storedToken = localStorage.getItem('ep_token')

        if (storedUser && storedToken) {
          const parsedUser = JSON.parse(storedUser)
          setUser(parsedUser)

          // Re-fetch onboarding state from the server so the router can
          // decide which page to land on without an extra user action.
          try {
            const me = await fetchMe(storedToken)
            setOnboardingState(me.onboarding_state ?? ONBOARDING_COLLECTING)
            setTrustScore(me.trust_score ?? 1.0)
          } catch {
            // /me failed (e.g. expired token) — leave onboardingState as
            // collecting so the app prompts for re-login rather than routing
            // to the dashboard with a stale state.
          }
        }
      } catch {
        localStorage.removeItem('ep_user')
        localStorage.removeItem('ep_token')
      } finally {
        setLoading(false)
      }
    }
    restoreUser()
  }, [])

  // ── Boot biometrics engine ─────────────────────────────────────────────────
  useEffect(() => {
    const ep = new EntropyPrimeClient()
    clientRef.current = ep

    ep.setUpdateCallback(({
      type, theta, eRec, trustScore: ts,
      drift, selectedFeatures: sf, featureNames,
    }) => {
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
  useEffect(() => {
    if (!user) return
    const id = setInterval(async () => {
      try {
        const ep = clientRef.current
        if (!ep) return

        const { eRec, trustScore: ts } = await ep.checkIdentity()
        const vec    = await ep.getLatentVector()
        const pStats = ep.getProfileStats()

        setProfileStats(pStats)
        setTrustScore(ts)

        // Pass the authoritative onboarding state to the server so it can
        // gate drift detection independently of the sample-count claim.
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
        })

        // Update our local state from the server's authoritative response.
        if (res.onboarding_state) {
          setOnboardingState(res.onboarding_state)
        }

        // Only trigger re-auth prompts when the profile is stable.
        // While collecting / syncing, log the anomaly but don't redirect.
        if (res.action === 'passive_reauth' || res.action === 'force_logout') {
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
        console.error('[AuthContext] Heartbeat failed:', err)
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [user, onboardingState, isProfileStable])

  // ── Actions ───────────────────────────────────────────────────────────────

  const login = useCallback((userData, token, serverOnboardingState) => {
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
    }
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

  return (
    <AuthCtx.Provider value={{
      // Identity
      user, loading, login, logout, restoreSession,
      // Biometrics engine
      epReady, liveTheta, trustScore, anomaly, sigCount,
      profileStats, liveDrift, selectedFeatures,
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