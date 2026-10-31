// 현재 도메인 정하기: 브라우저에 기억한 값이 없거나 틀려도 GET /domains로 올바르게 고르는지 확인한다.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { getStoredDomainId, resolveDomain, setStoredDomainId } from './currentDomain'
import { api } from './endpoints'
import type { Domain } from './types'

const domain = (id: string, name: string): Domain => ({
  domain_id: id,
  domain: name,
  verify_status: 'verified',
  txt_record: { name: `_a2d-verify.${name}`, value: 'a2d-verify=x' },
  verified_at: null,
  created_at: '2026-10-31T14:00:00+09:00',
})

afterEach(() => vi.restoreAllMocks())

describe('resolveDomain', () => {
  it('기억한 ID가 없으면(새 브라우저) 첫 번째 도메인을 고르고 기억한다', async () => {
    vi.spyOn(api.domains, 'list').mockResolvedValue({ items: [domain('DOM-7', 'a.test'), domain('DOM-8', 'b.test')] })
    const { current } = await resolveDomain()
    expect(current?.domain_id).toBe('DOM-7')
    expect(getStoredDomainId()).toBe('DOM-7')
  })

  it('기억한 ID가 목록에 있으면 그 도메인을 쓴다', async () => {
    setStoredDomainId('DOM-8')
    vi.spyOn(api.domains, 'list').mockResolvedValue({ items: [domain('DOM-7', 'a.test'), domain('DOM-8', 'b.test')] })
    expect((await resolveDomain()).current?.domain).toBe('b.test')
  })

  it('기억한 ID가 목록에 없으면(지워진 도메인) 첫 번째로 바꾼다', async () => {
    setStoredDomainId('DOM-99')
    vi.spyOn(api.domains, 'list').mockResolvedValue({ items: [domain('DOM-7', 'a.test')] })
    expect((await resolveDomain()).current?.domain_id).toBe('DOM-7')
    expect(getStoredDomainId()).toBe('DOM-7')
  })

  it('도메인이 하나도 없으면 null (화면은 등록으로 보낸다)', async () => {
    vi.spyOn(api.domains, 'list').mockResolvedValue({ items: [] })
    expect((await resolveDomain()).current).toBeNull()
  })
})
