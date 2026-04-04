import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginPage    from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ThreatPage   from './pages/ThreatPage'

function PrivateRoute({ children }) {
  const { user } = useAuth()
  return user ? children : <Navigate to="/login" replace />
}

function PublicRoute({ children }) {
  const { user } = useAuth()
  return !user ? children : <Navigate to="/dashboard" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={
            <PublicRoute><LoginPage /></PublicRoute>
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
