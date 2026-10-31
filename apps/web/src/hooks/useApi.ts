// 화면이 서버 데이터를 받는 기본 훅.
// 쓰는 법: const { data, loading, error, reload } = useApi(() => api.health(), [])
// deps가 바뀌면 다시 불러오고, reload()로 직접 다시 부를 수도 있다.

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface ApiState<T> {
  data: T | undefined
  loading: boolean
  error: ApiError | undefined
  reload: () => Promise<void>
}

export function useApi<T>(load: () => Promise<T>, deps: unknown[]): ApiState<T> {
  const [data, setData] = useState<T>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError>()

  // 가장 마지막 요청의 응답만 화면에 반영한다(빠르게 여러 번 부를 때 순서가 꼬이지 않게).
  const latest = useRef(0)

  const reload = useCallback(async () => {
    const id = ++latest.current
    setLoading(true)
    try {
      const result = await load()
      if (id === latest.current) {
        setData(result)
        setError(undefined)
      }
    } catch (e) {
      if (id === latest.current) {
        setError(e instanceof ApiError ? e : new ApiError(0, 'NETWORK', '서버에 연결하지 못했습니다.'))
      }
    } finally {
      if (id === latest.current) setLoading(false)
    }
    // load는 매번 새 함수라 deps로 다시 부를 시점을 정한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    void reload()
  }, [reload])

  return { data, loading, error, reload }
}
