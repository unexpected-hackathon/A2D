// 점검 중 배너에 보여 줄 Attack 에이전트의 최근 도구 호출. 감사 기록(GET /scans/{id}/audit?actor=attack)에서 만든다.
// 도구 이름은 사용자가 읽을 수 있는 말로 바꾸고, 가드가 막은 호출은 막힌 이유를 보여 준다.

import type { AuditEntry } from '../api/types'

const TOOL_LABEL: Record<string, string> = {
  list_assets: '자산 목록 확인',
  probe_http: '웹 응답과 API 주소 찾기',
  check_unauth_api: '로그인 없이 열리는 API 확인',
  finish_scan: '추가 점검 마침',
}

export interface TrailRow {
  key: string
  label: string
  detail: string
  rejected: boolean
}

export function agentTrail(entries: AuditEntry[], limit = 3): TrailRow[] {
  return entries
    .filter((e) => e.actor === 'attack')
    .slice(-limit)
    .map((e, i) => ({
      key: `${e.at}-${e.tool}-${i}`,
      label: TOOL_LABEL[e.tool] ?? e.tool,
      detail: e.rejected ? `가드가 막음: ${e.reject_reason ?? '이유 없음'}` : (e.result_summary ?? '결과 없음'),
      rejected: e.rejected,
    }))
}
