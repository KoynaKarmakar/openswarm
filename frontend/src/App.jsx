import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { getToken } from './api/client'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Assistant from './pages/Assistant'
import SwarmConsole from './pages/SwarmConsole'
import FraudAlerts from './pages/FraudAlerts'
import AuditTimeline from './pages/AuditTimeline'
import CaseQueue from './pages/CaseQueue'
import CoLendingEligibility from './pages/CoLendingEligibility'
import IdentityCredential from './pages/IdentityCredential'

function PrivateRoute({ children }) {
  return getToken() ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
        <Route path="/assistant"  element={<PrivateRoute><Assistant /></PrivateRoute>} />
        <Route path="/swarm"      element={<PrivateRoute><SwarmConsole /></PrivateRoute>} />
        <Route path="/fraud"      element={<PrivateRoute><FraudAlerts /></PrivateRoute>} />
        <Route path="/audit"      element={<PrivateRoute><AuditTimeline /></PrivateRoute>} />
        <Route path="/cases"      element={<PrivateRoute><CaseQueue /></PrivateRoute>} />
        <Route path="/clm"        element={<PrivateRoute><CoLendingEligibility /></PrivateRoute>} />
        <Route path="/identity"   element={<PrivateRoute><IdentityCredential /></PrivateRoute>} />
        <Route path="*"           element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
