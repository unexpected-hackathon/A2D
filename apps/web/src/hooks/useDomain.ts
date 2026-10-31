// 현재 도메인을 화면에서 꺼내 쓰는 훅. 값은 DomainProvider(DomainProvider.tsx)가 채운다.
// AppShell 안의 화면에서는 domain이 항상 있다(없으면 AppShell이 등록 화면으로 보낸다).

import { createContext, useContext } from 'react'
import type { Domain } from '../api/types'

export interface DomainState {
  domain: Domain
  domains: Domain[]
  select: (domainId: string) => void // 다른 도메인으로 바꾸기
  reload: () => Promise<void> // 목록을 다시 불러온다(도메인 삭제 뒤 등)
}

export const DomainContext = createContext<DomainState | null>(null)

export function useDomain(): DomainState {
  const ctx = useContext(DomainContext)
  if (!ctx) throw new Error('useDomain은 DomainProvider 안에서만 쓸 수 있습니다.')
  return ctx
}
