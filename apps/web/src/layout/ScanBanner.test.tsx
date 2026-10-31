// 점검 배너: 추가 점검 중에는 Attack 에이전트의 최근 도구 호출을 감사 기록에서 불러와 보여 주는지 확인한다.

import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/endpoints'
import type { AuditEntry, Scan } from '../api/types'
import { ScanContext, type ScanState } from '../hooks/useScan'
import { ScanBanner } from './ScanBanner'

afterEach(() => vi.restoreAllMocks())

const scan = (toolCalls: number): Scan => ({
  scan_id: 'S-0001',
  domain_id: 'DOM-1',
  status: toolCalls > 0 ? 'agent' : 'checking',
  stage: { name: toolCalls > 0 ? '추가 점검' : '기본 점검', done: 0, total: 1 },
  budget: { requests_used: 33, requests_limit: 300, tool_calls_used: toolCalls, tool_calls_limit: 20, elapsed_sec: 14, time_limit_sec: 300 },
  started_at: '2026-11-01T10:00:00+09:00',
  finished_at: null,
  safety_score: null,
  grade: null,
  error_message: null,
})

function renderBanner(running: Scan) {
  const state: ScanState = {
    domainId: 'DOM-1',
    running,
    isRunning: true,
    lastFinished: null,
    finishedVersion: 0,
    error: null,
    start: async () => {},
    stop: async () => {},
    dismissFinished: () => {},
  }
  return render(
    <ScanContext.Provider value={state}>
      <ScanBanner />
    </ScanContext.Provider>,
  )
}

const ENTRIES: AuditEntry[] = [
  { at: '2026-11-01T10:00:10+09:00', actor: 'attack', tool: 'list_assets', args: {}, result_summary: '자산 9개, 엔드포인트 0개', rejected: false, reject_reason: null },
  { at: '2026-11-01T10:00:12+09:00', actor: 'attack', tool: 'probe_http', args: { asset_id: 'A-003' }, result_summary: 'HTTP 200, 엔드포인트 3개(호출 가능 2)', rejected: false, reject_reason: null },
]

describe('ScanBanner 에이전트 기록', () => {
  it('도구를 부르기 시작하면 감사 기록을 불러와 최근 호출을 보여 준다', async () => {
    const audit = vi.spyOn(api.scans, 'audit').mockResolvedValue({ items: ENTRIES })
    renderBanner(scan(2))
    expect(await screen.findByText('웹 응답과 API 주소 찾기')).toBeInTheDocument()
    expect(screen.getByText('HTTP 200, 엔드포인트 3개(호출 가능 2)')).toBeInTheDocument()
    expect(screen.getByText('Attack 에이전트 · 도구 2/20회')).toBeInTheDocument()
    expect(audit).toHaveBeenCalledWith('S-0001', { actor: 'attack' })
  })

  it('기본 점검 중(도구 호출 0회)에는 감사 기록을 부르지 않는다', () => {
    const audit = vi.spyOn(api.scans, 'audit')
    renderBanner(scan(0))
    expect(screen.getByText('점검 중 · 기본 점검')).toBeInTheDocument()
    expect(screen.queryByText(/Attack 에이전트/)).not.toBeInTheDocument()
    expect(audit).not.toHaveBeenCalled()
  })
})
