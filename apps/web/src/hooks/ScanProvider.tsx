// 점검 진행 상태를 앱 전체가 나눠 쓰게 하는 곳 (5단계: 재점검 흐름).
//
// 흐름
//   재점검 버튼 → start() → POST /domains/{id}/scans (202, scan_id)
//   → 받은 점검 ID로 바로 한 번 check() → 진행 띠가 뜬다
//   → 그 뒤 2초마다 check() (usePolling)
//   → status가 done·stopped·failed가 되면 폴링을 멈추고 finishedVersion을 1 올린다
//   → 대시보드·기록 화면은 finishedVersion이 바뀌면 데이터를 다시 불러온다 → 점수가 오른다
//
// AppShell이 한 번 감싸고, 점검 진행 띠(ScanBanner)와 화면들이 useScan()으로 꺼내 쓴다.

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import { api } from '../api/endpoints'
import type { Scan } from '../api/types'
import { usePolling } from './usePolling'
import { ScanContext, type ScanState } from './useScan'

const POLL_MS = 2000
const TERMINAL = ['done', 'stopped', 'failed']

export function ScanProvider({ domainId, children }: { domainId: string | null; children: ReactNode }) {
  const [runningScanId, setRunningScanId] = useState<string | null>(null)
  const [running, setRunning] = useState<Scan | null>(null)
  const [lastFinished, setLastFinished] = useState<Scan | null>(null)
  const [finishedVersion, setFinishedVersion] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // 점검 하나의 상태를 묻고 화면 상태에 반영한다. 끝났으면 폴링을 멈춘다.
  const check = useCallback(async (scanId: string) => {
    try {
      const scan = await api.scans.get(scanId)
      if (TERMINAL.includes(scan.status)) {
        setRunningScanId(null)
        setRunning(null)
        setLastFinished(scan)
        setFinishedVersion((v) => v + 1)
      } else {
        setRunningScanId(scanId)
        setRunning(scan)
      }
    } catch {
      // 한 번 실패해도 다음 주기에 다시 묻는다.
    }
  }, [])

  // 화면을 새로 열었을 때 이미 돌고 있는 점검이 있으면 이어서 지켜본다.
  useEffect(() => {
    if (!domainId) return
    api.domains
      .summary(domainId)
      .then((s) => (s.running_scan_id ? check(s.running_scan_id) : undefined))
      .catch(() => undefined)
  }, [domainId, check])

  // 진행 중인 점검이 있는 동안 2초마다 묻는다.
  usePolling(() => (runningScanId ? check(runningScanId) : undefined), POLL_MS, runningScanId !== null)

  const start = useCallback(async () => {
    if (!domainId) return
    setError(null)
    setLastFinished(null)
    try {
      const started = await api.scans.start(domainId)
      setRunningScanId(started.scan_id)
      await check(started.scan_id) // 2초를 기다리지 않고 바로 진행 띠를 띄운다
    } catch (e) {
      if (e instanceof ApiError && e.code === 'SCAN_IN_PROGRESS') {
        // 이미 돌고 있으면 그 점검을 이어서 지켜본다.
        const s = await api.domains.summary(domainId)
        if (s.running_scan_id) await check(s.running_scan_id)
        return
      }
      setError(e instanceof ApiError ? e.message : '점검을 시작하지 못했습니다.')
    }
  }, [domainId, check])

  const stop = useCallback(async () => {
    if (!runningScanId) return
    await api.scans.stop(runningScanId).catch(() => undefined)
    await check(runningScanId)
  }, [runningScanId, check])

  const value: ScanState = {
    domainId,
    running,
    isRunning: runningScanId !== null,
    lastFinished,
    finishedVersion,
    error,
    start,
    stop,
    dismissFinished: () => setLastFinished(null),
  }
  return <ScanContext.Provider value={value}>{children}</ScanContext.Provider>
}
