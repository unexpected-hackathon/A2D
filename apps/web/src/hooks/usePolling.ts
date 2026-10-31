// active인 동안 intervalMs마다 tick()을 부른다. active가 false가 되면 멈춘다.
// 쓰는 곳: 점검이 진행 중일 때 2초마다 GET /scans/{id} (API 명세 5장)

import { useEffect, useRef } from 'react'

export function usePolling(tick: () => void | Promise<void>, intervalMs: number, active: boolean) {
  // 매 렌더마다 새로 만들어지는 tick을 최신 것으로 바꿔 끼운다(타이머를 다시 만들지 않으려고).
  const latestTick = useRef(tick)
  useEffect(() => {
    latestTick.current = tick
  })

  useEffect(() => {
    if (!active) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    // 앞 요청이 끝난 뒤 다음 요청을 예약한다(요청이 느려도 겹치지 않게).
    const run = async () => {
      await latestTick.current()
      if (!cancelled) timer = setTimeout(run, intervalMs)
    }
    timer = setTimeout(run, intervalMs)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [active, intervalMs])
}
