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

export const UNAUTHENTICATED_EVENT = 'a2d:unauthenticated'

type Method = 'GET' | 'POST' | 'PATCH'

export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const { status, data } = USE_MOCK
    ? await handleMock(method, path, body)
    : await callServer(method, path, body)

  if (status >= 200 && status < 300) {
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
    window.dispatchEvent(new CustomEvent(UNAUTHENTICATED_EVENT))
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
