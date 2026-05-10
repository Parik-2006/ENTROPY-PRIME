import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { EntropyPrimeClient } from '../services/biometrics'
import { sendWatchdogHeartbeat } from '../services/api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user,       setUser]       = useState(() => {
    try { return JSON.parse(localStorage.getItem('ep_user')) } catch { return null }
  })
  const [epReady,    setEpReady]    = useState(false)
  const [liveTheta,  setLiveTheta]  = useState(null)
  const [trustScore, setTrustScore] = useState(1.0)
  const [anomaly,    setAnomaly]    = useState(null)
  const [sigCount,   setSigCount]   = useState(0)
<<<<<<< Updated upstream
=======
  const [profileStats, setProfileStats] = useState(null)
  const [liveDrift,  setLiveDrift]  = useState(0)
  const [selectedFeatures, setSelectedFeatures] = useState([])
  const [sessionSecurity, setSessionSecurity] = useState({
    status: 'ok',
    action: 'ok',
    reason: 'Session trusted',
    sensitiveAccess: true,
    checkedAt: null,
  })
>>>>>>> Stashed changes

  const clientRef = useRef(null)

  // Boot biometrics engine
  useEffect(() => {
    const ep = new EntropyPrimeClient()
    clientRef.current = ep

    ep.setUpdateCallback(({ type, theta, eRec, trustScore: ts }) => {
      if (type === 'ready')   setEpReady(true)
      if (type === 'score')   setLiveTheta(theta)
      if (type === 'anomaly') {
        setTrustScore(ts)
<<<<<<< Updated upstream
        setAnomaly({ eRec, ts, time: Date.now() })
=======
        setAnomaly({ eRec, ts, drift, time: Date.now() })
        setSessionSecurity({
          status: 'reauth_required',
          action: 'local_anomaly',
          reason: `Behavioral drift detected${drift !== undefined ? ` (${drift.toFixed(2)})` : ''}`,
          sensitiveAccess: false,
          checkedAt: Date.now(),
        })
>>>>>>> Stashed changes
      }
    })

    ep.init().catch(console.error)
    return () => ep.destroy()
  }, [])

  // Watchdog heartbeat every 30s when logged in
  useEffect(() => {
    if (!user) return
    const id = setInterval(async () => {
      try {
        const ep  = clientRef.current
        if (!ep) return
        const vec = await ep.getLatentVector()
        const res = await sendWatchdogHeartbeat({
          userId:        user.id,
          latentVector:  vec,
          eRec:          ep.watchdog?.lastERec ?? 0,
          trustScore:    ep.watchdog?.trustScore ?? 1,
        })
<<<<<<< Updated upstream
        setTrustScore(ep.watchdog?.trustScore ?? 1)
        if (res.action === 'passive_reauth') setAnomaly({ type: 'reauth', ...res })
=======

        const checkedAt = Date.now()
        if (res.action === 'ok') {
          setAnomaly(null)
          setSessionSecurity({
            status: 'ok',
            action: res.action,
            reason: res.reason || 'Watchdog cleared session',
            sensitiveAccess: true,
            checkedAt,
          })
        }

        if (res.action === 'passive_reauth') {
          setAnomaly({ type: 'reauth', ...res, time: checkedAt })
          setSessionSecurity({
            status: 'reauth_required',
            action: res.action,
            reason: res.reason || 'Watchdog requested re-authentication',
            sensitiveAccess: false,
            checkedAt,
          })
        }

        if (res.action === 'disable_sensitive_api') {
          setAnomaly({ type: 'restricted', ...res, time: checkedAt })
          setSessionSecurity({
            status: 'restricted',
            action: res.action,
            reason: res.reason || 'Sensitive actions disabled by watchdog',
            sensitiveAccess: false,
            checkedAt,
          })
        }

        if (res.action === 'force_logout' || res.session_invalidated) {
          localStorage.removeItem('ep_token')
          localStorage.removeItem('ep_user')
          setUser(null)
          setTrustScore(0)
          setAnomaly({ type: 'force_logout', ...res, time: checkedAt })
          setProfileStats(null)
          setSelectedFeatures([])
          setSessionSecurity({
            status: 'locked',
            action: 'force_logout',
            reason: res.reason || 'Session invalidated by watchdog',
            sensitiveAccess: false,
            checkedAt,
          })
        }

        // Periodically sync profile to server (every 5th heartbeat)
        if (Math.random() < 0.2) {
        }
>>>>>>> Stashed changes
      } catch {}
    }, 30_000)
    return () => clearInterval(id)
  }, [user])

  const login = useCallback((userData, token) => {
    localStorage.setItem('ep_token', token)
    localStorage.setItem('ep_user',  JSON.stringify(userData))
    setUser(userData)
    setTrustScore(1.0)
    setAnomaly(null)
<<<<<<< Updated upstream
    // Increment session count for demo
=======
    setSessionSecurity({
      status: 'ok',
      action: 'ok',
      reason: 'New session started',
      sensitiveAccess: true,
      checkedAt: Date.now(),
    })
>>>>>>> Stashed changes
    setSigCount(c => c + 1)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('ep_token')
    localStorage.removeItem('ep_user')
    setUser(null)
    setTrustScore(1.0)
    setAnomaly(null)
<<<<<<< Updated upstream
=======
    setProfileStats(null)
    setSelectedFeatures([])
    setSessionSecurity({
      status: 'ok',
      action: 'logout',
      reason: 'Session closed',
      sensitiveAccess: true,
      checkedAt: Date.now(),
    })
>>>>>>> Stashed changes
  }, [])

  const getClient = useCallback(() => clientRef.current, [])

  return (
    <AuthCtx.Provider value={{
      user, login, logout,
      epReady, liveTheta, trustScore, anomaly, sigCount,
<<<<<<< Updated upstream
=======
      profileStats, liveDrift, selectedFeatures, sessionSecurity,
>>>>>>> Stashed changes
      getClient,
    }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
