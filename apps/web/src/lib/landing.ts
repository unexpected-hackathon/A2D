// 로그인한 뒤 어디로 갈지 정한다 (정보 구조도 1장 "진입").
// 도메인이 없으면 등록 화면, 있으면(현재 도메인을 기억해 두고) 대시보드.

import { resolveDomain } from '../api/currentDomain'

export async function landingPath(): Promise<string> {
  const { current } = await resolveDomain()
  return current ? '/dashboard' : '/register'
}
