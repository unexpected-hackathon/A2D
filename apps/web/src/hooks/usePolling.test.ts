// 점검 진행을 2초마다 묻는 폴링 훅이 켜고 끄는 대로 동작하는지 확인한다.

import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePolling } from './usePolling'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('usePolling', () => {
  it('켜져 있는 동안 주기마다 부른다', async () => {
    const tick = vi.fn()
    renderHook(() => usePolling(tick, 2000, true))
    await vi.advanceTimersByTimeAsync(6000)
    expect(tick).toHaveBeenCalledTimes(3)
  })

  it('꺼져 있으면 부르지 않는다', async () => {
    const tick = vi.fn()
    renderHook(() => usePolling(tick, 2000, false))
    await vi.advanceTimersByTimeAsync(6000)
    expect(tick).not.toHaveBeenCalled()
  })

  it('중간에 끄면 그 뒤로는 멈춘다', async () => {
    const tick = vi.fn()
    const { rerender } = renderHook(({ active }) => usePolling(tick, 2000, active), { initialProps: { active: true } })
    await vi.advanceTimersByTimeAsync(2000)
    rerender({ active: false })
    await vi.advanceTimersByTimeAsync(6000)
    expect(tick).toHaveBeenCalledTimes(1)
  })

  it('앞 요청이 느리면 끝난 뒤에 다음을 예약한다(겹치지 않는다)', async () => {
    let running = 0
    let maxConcurrent = 0
    const tick = vi.fn(async () => {
      running++
      maxConcurrent = Math.max(maxConcurrent, running)
      await new Promise((r) => setTimeout(r, 5000))
      running--
    })
    renderHook(() => usePolling(tick, 2000, true))
    await vi.advanceTimersByTimeAsync(20_000)
    expect(maxConcurrent).toBe(1)
  })
})
