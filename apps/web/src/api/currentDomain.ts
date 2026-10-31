// 지금 보고 있는 도메인을 정한다.
//
// 기준은 서버의 GET /domains(내 도메인 목록)이고, 브라우저에는 "마지막으로 본 도메인 ID"만 기억해 둔다.
//   - 기억한 ID가 목록에 있으면 그 도메인
//   - 없거나(새 브라우저, 저장이 지워짐) 목록에 없으면 첫 번째 도메인을 고르고 기억한다
//   - 목록이 비어 있으면 null → 화면은 등록으로 보낸다

import { api } from './endpoints'
import type { Domain } from './types'

const KEY = 'a2d.domainId'

export function getStoredDomainId(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setStoredDomainId(domainId: string) {
  try {
    localStorage.setItem(KEY, domainId)
  } catch {
    // 저장이 막힌 브라우저에서는 이번 화면에서만 쓴다.
  }
}

export interface ResolvedDomain {
  current: Domain | null
  domains: Domain[]
}

export async function resolveDomain(): Promise<ResolvedDomain> {
  const { items } = await api.domains.list()
  const stored = getStoredDomainId()
  const current = items.find((d) => d.domain_id === stored) ?? items[0] ?? null
  if (current && current.domain_id !== stored) setStoredDomainId(current.domain_id)
  return { current, domains: items }
}
