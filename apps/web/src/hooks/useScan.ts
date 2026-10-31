// 점검 진행 상태를 화면에서 꺼내 쓰는 훅. 값은 ScanProvider(ScanProvider.tsx)가 채운다.
// 컴포넌트와 훅을 다른 파일에 두어야 개발 중 빠른 새로고침(Fast Refresh)이 동작한다.

import { createContext, useContext } from 'react'
import type { Scan } from '../api/types'

export interface ScanState {
  domainId: string | null
  running: Scan | null // 진행 중인 점검의 최신 상태
  isRunning: boolean
  lastFinished: Scan | null // 방금 끝난 점검 (알림용)
  finishedVersion: number // 점검이 끝날 때마다 1씩 오른다
  error: string | null
  start: () => Promise<void>
  stop: () => Promise<void>
  dismissFinished: () => void
}

export const ScanContext = createContext<ScanState | null>(null)

export function useScan(): ScanState {
  const ctx = useContext(ScanContext)
  if (!ctx) throw new Error('useScan은 ScanProvider 안에서만 쓸 수 있습니다.')
  return ctx
}
