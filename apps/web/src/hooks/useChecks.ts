// 점검 항목 34개의 이름. 발견 ID의 check_id를 화면 이름으로 바꿀 때 쓴다.
// 처음 한 번만 서버에 묻고, 이후에는 같은 결과를 다시 쓴다.

import { api } from '../api/endpoints'
import type { Check } from '../api/types'
import { useApi } from './useApi'

let cached: Promise<{ items: Check[] }> | null = null

export function useCheckName(): (id: number) => string {
  const { data } = useApi(() => (cached ??= api.checks()), [])
  return (id) => data?.items.find((c) => c.check_id === id)?.name ?? `#${id}`
}
