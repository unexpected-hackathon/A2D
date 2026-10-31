// 점검 항목 34개의 이름. 발견 ID의 check_id를 화면 이름으로 바꿀 때 쓴다.
// 처음 한 번만 서버에 묻고, 이후에는 같은 결과를 다시 쓴다. 실패하면 기억을 지워 다음에 다시 묻는다.

import { api } from '../api/endpoints'
import type { Check } from '../api/types'
import { useApi } from './useApi'

let cached: Promise<{ items: Check[] }> | null = null

function loadChecks() {
  return api.checks().catch((e) => {
    cached = null // 실패한 결과를 계속 들고 있지 않는다(예: 세션 만료 직후)
    throw e
  })
}

export function useCheckName(): (id: number) => string {
  const { data } = useApi(() => (cached ??= loadChecks()), [])
  return (id) => data?.items.find((c) => c.check_id === id)?.name ?? `#${id}`
}
