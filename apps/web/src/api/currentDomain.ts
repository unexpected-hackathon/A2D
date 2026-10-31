// 지금 보고 있는 도메인 ID.
// API 명세에 "내 도메인 목록" API가 아직 없어서, 등록할 때 받은 ID를 브라우저에 기억해 둔다.
// 가짜 응답 모드에서는 시연 도메인(DOM-1)으로 시작한다.

const KEY = 'a2d.domainId'

export function getCurrentDomainId(): string | null {
  try {
    return localStorage.getItem(KEY) ?? (import.meta.env.VITE_USE_MOCK !== 'false' ? 'DOM-1' : null)
  } catch {
    return null
  }
}

export function setCurrentDomainId(domainId: string) {
  try {
    localStorage.setItem(KEY, domainId)
  } catch {
    // 저장이 막힌 브라우저에서는 이번 화면에서만 쓴다.
  }
}
