import { Routes, Route, Navigate } from 'react-router-dom'
import SubmitJob from './pages/SubmitJob'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import EmailPreview from './pages/EmailPreview'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<SubmitJob />} />
      <Route path="/auth/login" element={<Login />} />
      <Route path="/admin" element={<Dashboard />} />
      <Route path="/admin/email-queue/:id/preview" element={<EmailPreview />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
