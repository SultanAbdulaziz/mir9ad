import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import UserPage from './pages/user/UserPage'
import AdminPage from './pages/admin/AdminPage'

function RTLSync() {
  const { i18n } = useTranslation()
  useEffect(() => {
    const dir = i18n.language === 'ar' ? 'rtl' : 'ltr'
    document.documentElement.dir = dir
    document.documentElement.lang = i18n.language
  }, [i18n.language])
  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <RTLSync />
      <Routes>
        <Route path="/user"  element={<UserPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="*"      element={<Navigate to="/user" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
