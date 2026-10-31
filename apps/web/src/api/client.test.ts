// client.ts가 실제 서버 모드(VITE_USE_MOCK=false)에서 응답·오류를 어떻게 다루는지 확인한다.
// fetch를 가짜로 바꿔 서버 응답을 흉내 낸다.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type ClientModule = typeof import('./client')
let client: ClientModule

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue(new Response(body === undefined ? null : JSON.stringify(body), { status }))
}

beforeEach(async () => {
  vi.stubEnv('VITE_USE_MOCK', 'false')
  vi.resetModules() // USE_MOCK은 불러올 때 정해지므로 다시 불러온다
  client = await import('./client')
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('request', () => {
  it('실제 서버 모드면 /api/v1 아래로 JSON을 보내고 쿠키를 같이 보낸다', async () => {
    const fetchMock = respond(200, { ok: true })
    vi.stubGlobal('fetch', fetchMock)

    const data = await client.request('POST', '/auth/login', { email: 'a@b.c', password: 'p' })

    expect(client.USE_MOCK).toBe(false)
    expect(data).toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/auth/login')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(init.body)).toEqual({ email: 'a@b.c', password: 'p' })
  })

  it('본문 없는 요청에는 Content-Type을 붙이지 않는다', async () => {
    const fetchMock = respond(204)
    vi.stubGlobal('fetch', fetchMock)
    await expect(client.request('POST', '/auth/logout')).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][1].headers).toBeUndefined()
  })

  it('오류 응답은 명세의 code·message를 담은 ApiError로 던진다', async () => {
    vi.stubGlobal('fetch', respond(409, { error: { code: 'SCAN_IN_PROGRESS', message: '이미 진행 중인 점검이 있습니다.' } }))
    const error = (await client.request('POST', '/domains/DOM-1/scans').catch((e) => e)) as InstanceType<typeof client.ApiError>
    expect(error).toBeInstanceOf(client.ApiError)
    expect(error.status).toBe(409)
    expect(error.code).toBe('SCAN_IN_PROGRESS')
    expect(error.message).toBe('이미 진행 중인 점검이 있습니다.')
  })

  it('401 UNAUTHENTICATED면 로그인 화면으로 보내라는 이벤트를 알린다', async () => {
    vi.stubGlobal('fetch', respond(401, { error: { code: 'UNAUTHENTICATED', message: '다시 로그인해 주세요.' } }))
    const listener = vi.fn()
    window.addEventListener(client.UNAUTHENTICATED_EVENT, listener)
    await client.request('GET', '/auth/me').catch(() => undefined)
    window.removeEventListener(client.UNAUTHENTICATED_EVENT, listener)
    expect(listener).toHaveBeenCalledOnce()
  })

  it('로그인 실패(401 INVALID_CREDENTIALS)는 이벤트를 알리지 않는다', async () => {
    vi.stubGlobal('fetch', respond(401, { error: { code: 'INVALID_CREDENTIALS', message: '이메일 또는 비밀번호가 맞지 않습니다.' } }))
    const listener = vi.fn()
    window.addEventListener(client.UNAUTHENTICATED_EVENT, listener)
    await client.request('POST', '/auth/login', {}).catch(() => undefined)
    window.removeEventListener(client.UNAUTHENTICATED_EVENT, listener)
    expect(listener).not.toHaveBeenCalled()
  })

  it('오류 본문이 없으면 기본 문구를 쓴다', async () => {
    vi.stubGlobal('fetch', respond(500))
    const error = (await client.request('GET', '/health').catch((e) => e)) as InstanceType<typeof client.ApiError>
    expect(error.code).toBe('UNKNOWN')
    expect(error.message).toContain('다시 시도')
  })
})
