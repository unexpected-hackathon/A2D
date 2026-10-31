// 점검 중 Attack 에이전트의 감사 기록을 불러온다. 도구 호출 수(budget.tool_calls_used)가 바뀔 때만 다시 부른다.
// 에이전트가 아직 도구를 부르지 않았거나(기본 점검 중, 건너뜀) 점검이 없으면 빈 목록이다.

import { useEffect, useState } from 'react'
import { api } from '../api/endpoints'
import type { AuditEntry, Scan } from '../api/types'

export function useAgentTrail(scan: Scan | null): AuditEntry[] {
  const scanId = scan?.scan_id ?? null
  const calls = scan?.budget.tool_calls_used ?? 0
  const [loaded, setLoaded] = useState<{ scanId: string; items: AuditEntry[] } | null>(null)

  useEffect(() => {
    if (!scanId || calls === 0) return
    let alive = true
    api.scans
      .audit(scanId, { actor: 'attack' })
      .then((r) => {
        if (alive) setLoaded({ scanId, items: r.items })
      })
      .catch(() => {}) // 배너의 보조 정보라 실패해도 알리지 않는다. 다음 도구 호출 때 다시 부른다
    return () => {
      alive = false
    }
  }, [scanId, calls])

  return scanId && calls > 0 && loaded?.scanId === scanId ? loaded.items : []
}
