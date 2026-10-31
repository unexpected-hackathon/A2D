import { describe, expect, it } from 'vitest'
import type { AuditEntry } from '../api/types'
import { agentTrail } from './agentTrail'

const entry = (tool: string, extra: Partial<AuditEntry> = {}): AuditEntry => ({
  at: '2026-11-01T10:00:00+09:00',
  actor: 'attack',
  tool,
  args: {},
  result_summary: '완료',
  rejected: false,
  reject_reason: null,
  ...extra,
})

describe('agentTrail', () => {
  it('Attack 기록만 최근 것부터 정한 개수만큼 남기고 도구 이름을 바꾼다', () => {
    const rows = agentTrail([
      entry('list_assets', { result_summary: '자산 9개' }),
      entry('ask', { actor: 'defense' }),
      entry('probe_http', { result_summary: 'HTTP 200, 엔드포인트 3개' }),
      entry('check_unauth_api', { result_summary: '인증 필요(401), 이상 없음' }),
      entry('finish_scan', { result_summary: '추가 점검 종료: 더 볼 곳 없음' }),
    ])
    expect(rows.map((r) => r.label)).toEqual(['웹 응답과 API 주소 찾기', '로그인 없이 열리는 API 확인', '추가 점검 마침'])
    expect(rows[0].detail).toBe('HTTP 200, 엔드포인트 3개')
  })

  it('가드가 막은 호출은 막힌 이유를 보여 주고, 모르는 도구는 이름 그대로 둔다', () => {
    const [blocked, unknown] = agentTrail([
      entry('probe_http', { rejected: true, result_summary: null, reject_reason: '소유권이 확인된 자산이 아님: A-099' }),
      entry('new_tool'),
    ])
    expect(blocked).toMatchObject({ rejected: true, detail: '가드가 막음: 소유권이 확인된 자산이 아님: A-099' })
    expect(unknown.label).toBe('new_tool')
  })
})
