// 주소 → 화면 연결 (정보 구조도 1장).
// 로그인·등록은 공통 틀 없이, 나머지는 AppShell(왼쪽 메뉴) 안에 그린다.

import { useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { UNAUTHENTICATED_EVENT, type UnauthenticatedDetail } from './api/client'
import { AppShell } from './layout/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { DevApiPage } from './pages/DevApiPage'
import { GuidePage } from './pages/GuidePage'
import { HistoryPage } from './pages/HistoryPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'

export default function App() {
  const navigate = useNavigate()

  // 어느 화면에서든 401이 오면 로그인 화면으로 보낸다 (client.ts가 알려 준다).
  // "다시 로그인해 주세요."는 쓰는 도중 세션이 끝났을 때만 띄운다. 처음 들어온 사람에게는 띄우지 않는다.
  useEffect(() => {
    const toLogin = (e: Event) => {
      const expired = (e as CustomEvent<UnauthenticatedDetail>).detail?.expired ?? false
      navigate('/login', { replace: true, state: { expired } })
    }
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
