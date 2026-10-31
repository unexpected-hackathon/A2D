// 현재 도메인을 앱 전체가 나눠 쓰게 하는 곳.
//
// 흐름: GET /domains → resolveDomain()이 현재 도메인을 고른다
//   - 불러오는 중이면 로딩, 실패하면 오류와 "다시 시도"
//   - 도메인이 하나도 없으면 등록 화면으로 보낸다
//   - 도메인을 바꾸면(select) 기억해 두고 다시 고른다 → 화면들이 새 도메인으로 다시 불러온다

import { Skeleton, VStack } from '@seed-design/react'
import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { Callout } from 'seed-design/ui/callout'
import { resolveDomain, setStoredDomainId } from '../api/currentDomain'
import { useApi } from './useApi'
import { DomainContext, type DomainState } from './useDomain'

export function DomainProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0)
  const { data, error, reload } = useApi(resolveDomain, [version])

  const select = useCallback((domainId: string) => {
    setStoredDomainId(domainId)
    setVersion((v) => v + 1)
  }, [])

  const value = useMemo<DomainState | null>(
    () => (data?.current ? { domain: data.current, domains: data.domains, select } : null),
    [data, select],
  )

  if (error) {
    return (
      <VStack p="x8">
        <Callout
          tone="critical"
          title="도메인 목록을 불러오지 못했습니다"
          description={error.message}
          linkProps={{ children: '다시 시도', onClick: () => void reload() }}
        />
      </VStack>
    )
  }
  if (!data) {
    return (
      <VStack gap="x4" p="x8">
        <Skeleton radius="16" height="64px" width="full" />
        <Skeleton radius="16" height="320px" width="full" />
      </VStack>
    )
  }
  if (!value) return <Navigate to="/register" replace />

  return <DomainContext.Provider value={value}>{children}</DomainContext.Provider>
}
