// 가짜 서버가 API 명세대로 응답하고, 시연 흐름(재점검 → 점수 상승 → 새 노출 알림)을 흉내 내는지 확인한다.
// 가짜 서버는 일부러 기다렸다 응답하고 점검 진행을 시각으로 계산하므로, 가짜 시계를 쓴다.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Changes, ItemList, Scan, Summary } from '../types'

type HandleMock = typeof import('./server').handleMock
let handleMock: HandleMock

// 요청 하나를 보내고 응답 지연만큼 시계를 돌린다.
async function call<T = unknown>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown) {
  const pending = handleMock(method, path, body)
  await vi.advanceTimersByTimeAsync(500)
  const res = await pending
  return res as { status: number; data: T }
}

// 점검을 시작하고 끝날 때까지 시계를 돌린 뒤 요약을 돌려준다.
async function rescan() {
  const started = await call<{ scan_id: string }>('POST', '/domains/DOM-1/scans')
  expect(started.status).toBe(202)
  await vi.advanceTimersByTimeAsync(10_000)
  const scan = await call<Scan>('GET', `/scans/${started.data.scan_id}`)
  expect(scan.data.status).toBe('done')
  return { scanId: started.data.scan_id, summary: (await call<Summary>('GET', '/domains/DOM-1/summary')).data }
}

beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules() // 테스트마다 서버 상태를 처음으로
  ;({ handleMock } = await import('./server'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('시연 흐름', () => {
  it('처음에는 20 F, 오늘 할 일은 #16 → #8 → #18', async () => {
    const { data } = await call<Summary>('GET', '/domains/DOM-1/summary')
    expect(data.safety_score).toBe(20)
    expect(data.grade).toBe('F')
    expect(data.today_tasks.map((t) => [t.check_id, t.safety_score_after])).toEqual([
      [16, 30],
      [8, 49],
      [18, 100],
    ])
  })

  it('재점검할 때마다 1번을 고친 것으로 보고 30 → 49 → 100으로 오른다', async () => {
    const scores = []
    for (let i = 0; i < 3; i++) scores.push((await rescan()).summary.safety_score)
    expect(scores).toEqual([30, 49, 100])
  })

  it('변화에서 고친 발견이 "해결됨"으로 나온다', async () => {
    const { scanId } = await rescan()
    const { data } = await call<Changes>('GET', `/scans/${scanId}/changes`)
    expect(data.safety_score).toEqual({ before: 20, after: 30 })
    expect(data.resolved_findings.map((f) => f.check_id)).toEqual([16])
    expect(data.new_findings).toEqual([])
  })

  it('모두 고친 뒤 재점검하면 새 테스트 서버가 열려 새 노출 알림이 뜬다', async () => {
    for (let i = 0; i < 3; i++) await rescan()
    const { summary } = await rescan()
    expect(summary.alerts.map((a) => a.type)).toEqual(['new_asset', 'new_finding'])
    expect(summary.today_tasks[0].check_id).toBe(19)
  })

  it('점검 중에는 단계 이름과 진행 상태를 돌려준다', async () => {
    const started = await call<{ scan_id: string }>('POST', '/domains/DOM-1/scans')
    await vi.advanceTimersByTimeAsync(2_000)
    const { data } = await call<Scan>('GET', `/scans/${started.data.scan_id}`)
    expect(['discovering', 'checking']).toContain(data.status)
    expect(data.safety_score).toBeNull()
  })
})

describe('오류 응답 (명세 1장)', () => {
  it('점검 중에 또 시작하면 409 SCAN_IN_PROGRESS', async () => {
    await call('POST', '/domains/DOM-1/scans')
    const res = await call<{ error: { code: string } }>('POST', '/domains/DOM-1/scans')
    expect(res.status).toBe(409)
    expect(res.data.error.code).toBe('SCAN_IN_PROGRESS')
  })

  it('끝나지 않은 점검의 조치 가이드는 409 SCAN_NOT_FINISHED', async () => {
    const started = await call<{ scan_id: string }>('POST', '/domains/DOM-1/scans')
    const res = await call<{ error: { code: string } }>('GET', `/scans/${started.data.scan_id}/report`)
    expect(res.status).toBe(409)
    expect(res.data.error.code).toBe('SCAN_NOT_FINISHED')
  })

  it('소유권 확인 전 점검은 409 DOMAIN_NOT_VERIFIED', async () => {
    const created = await call<{ domain_id: string }>('POST', '/domains', { domain: 'new.example' })
    const res = await call<{ error: { code: string } }>('POST', `/domains/${created.data.domain_id}/scans`)
    expect(res.data.error.code).toBe('DOMAIN_NOT_VERIFIED')
  })

  it('도메인 형식이 틀리면 400, 같은 도메인을 다시 등록하면 기존 것을 200으로', async () => {
    expect((await call('POST', '/domains', { domain: 'not a domain' })).status).toBe(400)
    const again = await call<{ domain_id: string }>('POST', '/domains', { domain: 'jobnest.test' })
    expect(again.status).toBe(200)
    expect(again.data.domain_id).toBe('DOM-1')
  })

  it('없는 주소는 404', async () => {
    expect((await call('GET', '/findings/F-9999')).status).toBe(404)
  })
})

describe('인증 (명세 3장)', () => {
  it('로그아웃하면 401, 다시 로그인하면 통과', async () => {
    expect((await call('POST', '/auth/logout')).status).toBe(204)
    expect((await call('GET', '/auth/me')).status).toBe(401)
    expect((await call('GET', '/health')).status).toBe(200) // 공개 API
    const login = await call('POST', '/auth/login', { email: 'admin@jobnest.test', password: 'a2d-demo' })
    expect(login.status).toBe(200)
    expect((await call('GET', '/auth/me')).status).toBe(200)
  })

  it('비밀번호가 틀리면 401, 5번 틀리면 429로 잠긴다', async () => {
    for (let i = 0; i < 5; i++) {
      const res = await call<{ error: { code: string } }>('POST', '/auth/login', { email: 'admin@jobnest.test', password: 'x' })
      expect(res.data.error.code).toBe('INVALID_CREDENTIALS')
    }
    const locked = await call<{ error: { code: string } }>('POST', '/auth/login', { email: 'admin@jobnest.test', password: 'a2d-demo' })
    expect(locked.status).toBe(429)
  })

  it('GET /domains는 내 도메인 목록을 돌려준다', async () => {
    const { data } = await call<ItemList<{ domain: string }>>('GET', '/domains')
    expect(data.items.map((d) => d.domain)).toEqual(['jobnest.test'])
  })
})

describe('자산 중요도 수정', () => {
  it('api 자산 중요도를 4로 낮추면 안전 점수가 다시 계산된다', async () => {
    const res = await call<{ summary: { safety_score: number } }>('PATCH', '/domains/DOM-1/assets/A-002', { importance: 4 })
    expect(res.status).toBe(200)
    expect(res.data.summary.safety_score).toBeGreaterThan(20)
  })

  it('1~5 밖이면 400', async () => {
    expect((await call('PATCH', '/domains/DOM-1/assets/A-002', { importance: 9 })).status).toBe(400)
  })
})
