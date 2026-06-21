import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { TrustProvider } from './context/TrustContext'
import { BankProvider } from './context/BankContext'

// Public / onboarding
import LoginPage   from './pages/LoginPage'
import EnrollPage  from './pages/EnrollPage'

// New product shell + pages
import AppShell      from './components/AppShell'
import BankDashboard from './pages/bank/Dashboard'
import Accounts      from './pages/bank/Accounts'
import Transfers     from './pages/bank/Transfers'
import Settings      from './pages/bank/Settings'
import ComingSoon    from './pages/bank/ComingSoon'
import AiBanker      from './pages/bank/AiBanker'
import Journal       from './pages/bank/Journal'
import Profile       from './pages/bank/Profile'
import Beneficiaries from './pages/bank/Beneficiaries'
import Support       from './pages/bank/Support'
import SecurityCenter from './pages/security/SecurityCenter'
import ThreatIntel    from './pages/security/ThreatIntel'

// Legacy (kept reachable — nothing removed)
import ProfileBuildPage from './pages/ProfileBuildPage'
import DashboardPage    from './pages/DashboardPage'
import ThreatPage       from './pages/ThreatPage'
import AdminDashboard   from './pages/AdminDashboard'
import SiteManagement   from './pages/SiteManagement'

const loadScreen = (msg) => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--sans)' }}>{msg}</div>
)

function PrivateRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return loadScreen('Restoring session…')
  return user ? children : <Navigate to="/login" replace />
}

function PublicRoute({ children }) {
  const { user, loading, isProfileStable } = useAuth()
  if (loading) return loadScreen('Initializing…')
  if (user) return <Navigate to={isProfileStable ? '/app/dashboard' : '/enroll'} replace />
  return children
}

function SessionRestorer() {
  const { restoreSession } = useAuth()
  useEffect(() => { restoreSession() }, [])
  return null
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
       <TrustProvider>
        <BankProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <SessionRestorer />
          <Routes>
            {/* Public */}
            <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />

            {/* Onboarding */}
            <Route path="/enroll" element={<PrivateRoute><EnrollPage /></PrivateRoute>} />

            {/* New product surface */}
            <Route path="/app" element={<PrivateRoute><AppShell /></PrivateRoute>}>
              <Route index element={<Navigate to="/app/dashboard" replace />} />
              <Route path="dashboard"     element={<BankDashboard />} />
              <Route path="ai"            element={<AiBanker />} />
              <Route path="accounts"      element={<Accounts />} />
              <Route path="transfers"     element={<Transfers />} />
              <Route path="beneficiaries" element={<Beneficiaries />} />
              <Route path="journal"       element={<Journal />} />
              <Route path="support"       element={<Support />} />
              <Route path="profile"       element={<Profile />} />
              <Route path="security"      element={<SecurityCenter />} />
              <Route path="threats"       element={<ThreatIntel />} />
              <Route path="settings"      element={<Settings />} />
            </Route>

            {/* Legacy — preserved, reachable via Settings → Legacy/Advanced */}
            <Route path="/profile-build" element={<PrivateRoute><ProfileBuildPage /></PrivateRoute>} />
            <Route path="/dashboard"     element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
            <Route path="/threats"       element={<PrivateRoute><ThreatPage /></PrivateRoute>} />
            <Route path="/admin"         element={<PrivateRoute><AdminDashboard /></PrivateRoute>} />
            <Route path="/sites"         element={<PrivateRoute><SiteManagement /></PrivateRoute>} />

            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
        </BankProvider>
       </TrustProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
