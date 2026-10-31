// API 명세의 엔드포인트 21개와 백엔드가 더한 GET /domains를 함수 하나씩으로 옮겼다.
// 화면은 주소 문자열을 쓰지 않고 이 함수만 부른다. 예: api.scans.start(domainId)

import { request } from './client'
import type {
  Answer,
  Asset,
  AuditEntry,
  Changes,
  Check,
  Domain,
  FindingDetail,
  FindingSummary,
  Guide,
  Health,
  HistoryItem,
  ItemList,
  Scan,
  ScanStarted,
  SessionInfo,
  Severity,
  Summary,
  VerifyResult,
} from './types'

export interface FindingFilter {
  asset_id?: string
  severity?: Severity[]
  status?: string
  check_id?: number
}

function query(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') q.set(key, String(value))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // 3장 인증
  auth: {
    login: (email: string, password: string) =>
      request<SessionInfo>('POST', '/auth/login', { email, password }),
    logout: () => request<void>('POST', '/auth/logout'),
    me: () => request<SessionInfo>('GET', '/auth/me'),
  },

  // 4장 공통·도메인
  health: () => request<Health>('GET', '/health'),
  checks: () => request<ItemList<Check>>('GET', '/checks'),
  domains: {
    // 내 도메인 목록. API 명세에 없던 것을 백엔드 PR #14가 추가했다.
    list: () => request<ItemList<Domain>>('GET', '/domains'),
    create: (domain: string) => request<Domain>('POST', '/domains', { domain }),
    get: (domainId: string) => request<Domain>('GET', `/domains/${domainId}`),
    verify: (domainId: string) => request<VerifyResult>('POST', `/domains/${domainId}/verify`),
    remove: (domainId: string) => request<void>('DELETE', `/domains/${domainId}`),
    summary: (domainId: string) => request<Summary>('GET', `/domains/${domainId}/summary`),
    history: (domainId: string) =>
      request<ItemList<HistoryItem>>('GET', `/domains/${domainId}/history`),
    setAssetImportance: (domainId: string, assetId: string, importance: number) =>
      request<{ asset: Pick<Asset, 'asset_id' | 'importance'>; summary: Pick<Summary, 'safety_score' | 'grade'> }>(
        'PATCH',
        `/domains/${domainId}/assets/${assetId}`,
        { importance },
      ),
  },

  // 5장 점검
  scans: {
    start: (domainId: string) => request<ScanStarted>('POST', `/domains/${domainId}/scans`),
    get: (scanId: string) => request<Scan>('GET', `/scans/${scanId}`),
    stop: (scanId: string) => request<Scan>('POST', `/scans/${scanId}/stop`),
    assets: (scanId: string) => request<ItemList<Asset>>('GET', `/scans/${scanId}/assets`),
    findings: (scanId: string, filter: FindingFilter = {}) =>
      request<ItemList<FindingSummary>>(
        'GET',
        `/scans/${scanId}/findings${query({
          asset_id: filter.asset_id,
          severity: filter.severity?.join(','),
          status: filter.status,
          check_id: filter.check_id,
        })}`,
      ),
    guide: (scanId: string) => request<Guide>('GET', `/scans/${scanId}/report`),
    ask: (scanId: string, question: string) =>
      request<Answer>('POST', `/scans/${scanId}/questions`, { question }),
    changes: (scanId: string) => request<Changes>('GET', `/scans/${scanId}/changes`),
    audit: (scanId: string, filter: { actor?: string; rejected?: boolean } = {}) =>
      request<ItemList<AuditEntry>>(
        'GET',
        `/scans/${scanId}/audit${query({
          actor: filter.actor,
          rejected: filter.rejected === undefined ? undefined : String(filter.rejected),
        })}`,
      ),
  },

  // 7장 발견
  findings: {
    get: (findingId: string) => request<FindingDetail>('GET', `/findings/${findingId}`),
  },
}
