import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { currentToken } from './lib/auth'
import Login from './pages/Login'
import Inbox from './pages/Inbox'
import JobDetail from './pages/JobDetail'
import Studio from './pages/Studio'
import Pipeline from './pages/Pipeline'
import Messages from './pages/Messages'
import Run from './pages/Run'
import Analytics from './pages/Analytics'
import SettingsPage from './pages/Settings'
import Approvals from './pages/Approvals'

function RequireAuth({ children }: { children: React.ReactNode }) {
  return currentToken() ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/inbox" replace />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/jobs/:threadId" element={<JobDetail />} />
        <Route path="/studio/:threadId" element={<Studio />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/messages" element={<Messages />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/runs/:threadId" element={<Run />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/inbox" replace />} />
    </Routes>
  )
}
