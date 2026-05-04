import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginPage    from './pages/LoginPage'
import ProfileBuildPage from './pages/ProfileBuildPage'
import DashboardPage from './pages/DashboardPage'
import ThreatPage   from './pages/ThreatPage'

function PrivateRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0a0a0a', color: '#fff' }}>Restoring session...</div>
  return user ? children : <Navigate to="/login" replace />
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0a0a0a', color: '#fff' }}>Initializing...</div>
  return !user ? children : <Navigate to="/profile-build" replace />
}

function SessionRestorer() {
  const { restoreSession } = useAuth()
  useEffect(() => {
    restoreSession()
  }, [])
  return null
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <SessionRestorer />
        <Routes>
          <Route path="/login" element={
            <PublicRoute><LoginPage /></PublicRoute>
          }/>
          <Route path="/profile-build" element={
            <PrivateRoute><ProfileBuildPage /></PrivateRoute>
          }/>
          <Route path="/dashboard" element={
            <PrivateRoute><DashboardPage /></PrivateRoute>
          }/>
          <Route path="/threats" element={
            <PrivateRoute><ThreatPage /></PrivateRoute>
          }/>
          <Route path="*" element={<Navigate to="/login" replace />}/>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
