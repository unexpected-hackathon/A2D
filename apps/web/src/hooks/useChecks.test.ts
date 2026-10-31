// 점검 이름 기억: 처음 요청이 실패해도 다음에 다시 물어 이름을 보여 주는지 확인한다.

import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

beforeEach(() => vi.resetModules()) // 모듈에 기억한 값(cached)을 테스트마다 비운다

describe('useCheckName', () => {
  it('처음 /checks가 실패해도 다음에 쓰는 화면에서는 다시 물어 이름을 보여 준다', async () => {
    const { api } = await import('../api/endpoints')
    const { ApiError } = await import('../api/client')
    const { useCheckName } = await import('./useChecks')
    const spy = vi
      .spyOn(api, 'checks')
      .mockRejectedValueOnce(new ApiError(401, 'UNAUTHENTICATED', '다시 로그인해 주세요.'))
      .mockResolvedValue({ items: [{ check_id: 16, name: '인증 없는 API', category: 'C', category_name: '접근 통제', phase: '1차', scored: true }] })

    const first = renderHook(() => useCheckName())
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(first.result.current(16)).toBe('#16') // 실패했으니 번호로
    first.unmount()

    const second = renderHook(() => useCheckName())
    await waitFor(() => expect(second.result.current(16)).toBe('인증 없는 API'))
    expect(spy).toHaveBeenCalledTimes(2)
  })
})
