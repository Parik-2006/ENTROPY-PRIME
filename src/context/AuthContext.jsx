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
        setAnomaly({ eRec, ts, time: Date.now() })
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
        setTrustScore(ep.watchdog?.trustScore ?? 1)
        if (res.action === 'passive_reauth') setAnomaly({ type: 'reauth', ...res })
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
    // Increment session count for demo
    setSigCount(c => c + 1)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('ep_token')
    localStorage.removeItem('ep_user')
    setUser(null)
    setTrustScore(1.0)
    setAnomaly(null)
  }, [])

  const getClient = useCallback(() => clientRef.current, [])

  return (
    <AuthCtx.Provider value={{
      user, login, logout,
      epReady, liveTheta, trustScore, anomaly, sigCount,
      getClient,
    }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
