// 주소 → 화면 연결 (정보 구조도 1장).
// 로그인·등록은 공통 틀 없이, 나머지는 AppShell(왼쪽 메뉴) 안에 그린다.

import { useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { UNAUTHENTICATED_EVENT } from './api/client'
import { AppShell } from './layout/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { DevApiPage } from './pages/DevApiPage'
import { GuidePage } from './pages/GuidePage'
import { HistoryPage } from './pages/HistoryPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'

export default function App() {
  const navigate = useNavigate()

  // 어느 화면에서든 세션이 끝나 401이 오면 로그인 화면으로 보낸다 (client.ts가 알려 준다).
  useEffect(() => {
    const toLogin = () => navigate('/login', { replace: true, state: { expired: true } })
    window.addEventListener(UNAUTHENTICATED_EVENT, toLogin)
    return () => window.removeEventListener(UNAUTHENTICATED_EVENT, toLogin)
  }, [navigate])

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/guide" element={<GuidePage />} />
        <Route path="/guide/:scanId" element={<GuidePage />} />
        <Route path="/history" element={<HistoryPage />} />
        {import.meta.env.DEV && <Route path="/dev/api" element={<DevApiPage />} />}
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
