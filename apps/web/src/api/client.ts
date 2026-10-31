// 모든 서버 요청이 지나가는 단 하나의 함수.
// 화면은 이 파일을 직접 부르지 않고 endpoints.ts의 함수만 쓴다.
//
// 흐름: request() → (가짜 응답 모드면 mock/server.ts, 아니면 fetch('/api/v1/...'))
//       → 2xx면 JSON을 돌려주고, 아니면 ApiError를 던진다.
//       → 401이면 'a2d:unauthenticated' 이벤트를 알려 로그인 화면으로 보낼 수 있게 한다.

import { handleMock } from './mock/server'

const BASE = '/api/v1'

// .env.local의 VITE_USE_MOCK=false일 때만 진짜 서버로 보낸다.
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

// 이벤트의 detail.expired: 이 탭에서 로그인된 응답을 받은 뒤에 401이 왔는지.
// 처음 들어와 세션이 없을 때(false)와 쓰는 도중 세션이 끝났을 때(true)를 로그인 화면이 구분한다.
export const UNAUTHENTICATED_EVENT = 'a2d:unauthenticated'
export type UnauthenticatedDetail = { expired: boolean }

// 로그인 없이 부를 수 있는 주소. 이 응답으로는 세션이 있었는지 알 수 없다.
const PUBLIC_PATHS = new Set(['/health', '/auth/login', '/auth/logout'])
let hadSession = false

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE'

export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const { status, data } = USE_MOCK
    ? await handleMock(method, path, body)
    : await callServer(method, path, body)

  if (status >= 200 && status < 300) {
    if (path === '/auth/login') hadSession = true
    else if (path === '/auth/logout') hadSession = false
    else if (!PUBLIC_PATHS.has(path.split('?')[0])) hadSession = true
    return data as T
  }

  // 명세 1장 오류 형식: { error: { code, message } }
  const err = (data as { error?: { code?: string; message?: string } } | undefined)?.error
  const apiError = new ApiError(
    status,
    err?.code ?? 'UNKNOWN',
    err?.message ?? '요청을 처리하지 못했습니다. 잠시 뒤 다시 시도해 주세요.',
  )

  if (status === 401 && apiError.code === 'UNAUTHENTICATED') {
    // 여기서 hadSession을 지우지 않는다. 한 화면이 여러 요청을 동시에 보내면 401도 여러 번 오는데,
    // 첫 번째만 expired=true가 되고 뒤의 것이 false로 덮어쓰기 때문이다.
    const detail: UnauthenticatedDetail = { expired: hadSession }
    window.dispatchEvent(new CustomEvent(UNAUTHENTICATED_EVENT, { detail }))
  }
  throw apiError
}

async function callServer(method: Method, path: string, body?: unknown) {
  const res = await fetch(BASE + path, {
    method,
    // 같은 출처라 세션 쿠키가 자동으로 붙는다.
    credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  // 204(로그아웃)처럼 본문이 없는 응답도 있다.
  const text = await res.text()
  return { status: res.status, data: text ? JSON.parse(text) : undefined }
}
