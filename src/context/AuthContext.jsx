import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { EntropyPrimeClient } from '../services/biometrics'
import { sendWatchdogHeartbeat, logoutUser } from '../services/api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user,       setUser]       = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [epReady,    setEpReady]    = useState(false)
  const [liveTheta,  setLiveTheta]  = useState(null)
  const [trustScore, setTrustScore] = useState(1.0)
  const [anomaly,    setAnomaly]    = useState(null)
  const [sigCount,   setSigCount]   = useState(0)
  const [profileStats, setProfileStats] = useState(null)
  const [liveDrift,  setLiveDrift]  = useState(0)
  const [selectedFeatures, setSelectedFeatures] = useState([])

  const clientRef = useRef(null)

  // Restore session from localStorage on boot
  useEffect(() => {
    const restoreUser = async () => {
      try {
        const storedUser = localStorage.getItem('ep_user')
        const storedToken = localStorage.getItem('ep_token')
        
        if (storedUser && storedToken) {
          const parsedUser = JSON.parse(storedUser)
          // In a real app, we'd verify the token with the backend here
          setUser(parsedUser)
        }
      } catch (e) {
        console.error('Failed to restore session:', e)
        localStorage.removeItem('ep_user')
        localStorage.removeItem('ep_token')
      } finally {
        setLoading(false)
      }
    }
    restoreUser()
  }, [])


  // Boot biometrics engine
  useEffect(() => {
    const ep = new EntropyPrimeClient()
    clientRef.current = ep

    ep.setUpdateCallback(({ type, theta, eRec, trustScore: ts, drift, selectedFeatures: sf, featureNames }) => {
      if (type === 'ready')   setEpReady(true)
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

  // Restore per-user profile when user is already logged in
  useEffect(() => {
    if (user && clientRef.current) {
      clientRef.current.setUser(user.id)
    }
  }, [user])

  // Watchdog heartbeat every 30s with per-user profile drift info
  useEffect(() => {
    if (!user) return
    const id = setInterval(async () => {
      try {
        const ep = clientRef.current
        if (!ep) return

        // Full biometric check (autoencoder + behavioral profile drift)
        const { eRec, trustScore: ts } = await ep.checkIdentity()
        const vec    = await ep.getLatentVector()
        const pStats = ep.getProfileStats()

        setProfileStats(pStats)
        setTrustScore(ts)

        // Send heartbeat with per-user drift context
        const res = await sendWatchdogHeartbeat({
          userId:           user.id,
          latentVector:     vec,
          eRec,
          trustScore:       ts,
          behavioralDrift:  pStats.lastDrift,
          adaptiveThreshold: pStats.adaptiveThreshold,
          selectedFeatures: pStats.selectedFeatures,
          sampleCount:      pStats.sampleCount,
        })

        if (res.action === 'passive_reauth') setAnomaly({ type: 'reauth', ...res })

        // Periodically sync profile to server (every 5th heartbeat)
        if (Math.random() < 0.2) {
        }
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
    setSigCount(c => c + 1)
    // Load per-user biometric profile into engine
    if (clientRef.current) {
      clientRef.current.setUser(userData.id)
    }
  }, [])

  const logout = useCallback(() => {
    // Persist profile before logout
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
  }, [])

  const getClient = useCallback(() => clientRef.current, [])

  const restoreSession = useCallback(async () => {
    setLoading(true)
    try {
      const storedToken = localStorage.getItem('ep_token')
      const storedUser = localStorage.getItem('ep_user')
      if (storedToken && storedUser) {
        // Here we could add a call to /session/verify to ensure token is still valid
        setUser(JSON.parse(storedUser))
      }
    } catch (e) {
      logout()
    } finally {
      setLoading(false)
    }
  }, [logout])

  return (
    <AuthCtx.Provider value={{
      user, loading, login, logout, restoreSession,
      epReady, liveTheta, trustScore, anomaly, sigCount,
      profileStats, liveDrift, selectedFeatures,
      getClient,
    }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)


