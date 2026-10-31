// 로그인한 뒤 어디로 갈지 정한다 (정보 구조도 1장 "진입").
// 도메인이 없으면 등록 화면, 있으면 그 도메인을 현재 도메인으로 기억하고 대시보드.

import { getCurrentDomainId, setCurrentDomainId } from '../api/currentDomain'
import { api } from '../api/endpoints'

export async function landingPath(): Promise<string> {
  const { items } = await api.domains.list()
  if (items.length === 0) return '/register'
  const current = getCurrentDomainId()
  if (!items.some((d) => d.domain_id === current)) setCurrentDomainId(items[0].domain_id)
  return '/dashboard'
}
