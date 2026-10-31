// 로그인·등록을 뺀 모든 화면의 공통 틀 (정보 구조도 2장).
// 왼쪽: SEED SideNavigation (로고, 점검 대상 도메인, 메뉴 3개, 사용자 메뉴)
// 오른쪽: 맨 위 브랜드 줄 + 지금 주소의 화면(<Outlet />)

import {
  IconArrowLeftBracketRightLine,
  IconCheckmarkShieldFill,
  IconClockFill,
  IconChevronDownLine,
  IconHouseFill,
  IconPlusLine,
} from '@karrotmarket/react-monochrome-icon'
import { Box, HStack, Icon, Layout, Text, VStack, useSideNavigationContext } from '@seed-design/react'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { Avatar } from 'seed-design/ui/avatar'
import { Badge } from 'seed-design/ui/badge'
import { IdentityPlaceholder } from 'seed-design/ui/identity-placeholder'
import { MenuContent, MenuGroup, MenuItem, MenuRoot, MenuTrigger } from 'seed-design/ui/menu'
import {
  SideNavigationContent,
  SideNavigationFooter,
  SideNavigationGroup,
  SideNavigationHeader,
  SideNavigationInset,
  SideNavigationProvider,
  SideNavigationRoot,
  SideNavigationTrigger,
} from 'seed-design/ui/side-navigation'
import { api } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import logoUrl from '../assets/a2d-logo.svg'
import iconUrl from '../assets/a2d-icon.svg'
import { DomainProvider } from '../hooks/DomainProvider'
import { ScanProvider } from '../hooks/ScanProvider'
import { useDomain } from '../hooks/useDomain'
import { PageTransition } from './PageTransition'
import { ScanBanner } from './ScanBanner'

const NAV = [
  { path: '/dashboard', label: '대시보드', icon: <IconHouseFill /> },
  { path: '/guide', label: '조치 가이드', icon: <IconCheckmarkShieldFill /> },
  { path: '/history', label: '기록', icon: <IconClockFill /> },
]

function Brand() {
  const { collapsed } = useSideNavigationContext()
  return (
    <Box px="x2" py="x1">
      {collapsed ? (
        <img src={iconUrl} alt="A2D" width={32} height={32} style={{ borderRadius: 8, display: 'block' }} />
      ) : (
        <img src={logoUrl} alt="A2D" height={34} style={{ display: 'block' }} />
      )}
    </Box>
  )
}

// 점검 대상 카드. 누르면 다른 도메인으로 바꾸거나 새 도메인을 추가할 수 있다.
function DomainChip() {
  const { collapsed } = useSideNavigationContext()
  const { domain, domains, select } = useDomain()
  const navigate = useNavigate()
  if (collapsed) return null
  return (
    <Box px="x2" pb="x2">
      <MenuRoot>
        <MenuTrigger asChild>
          <VStack
            as="button"
            gap="x1"
            p="x3"
            borderRadius="r3"
            bg="bg.neutralWeak"
            width="full"
            aria-label={`점검 대상 ${domain.domain}, 바꾸거나 추가하기`}
            style={{ border: 0, cursor: 'pointer', textAlign: 'left', font: 'inherit' }}
          >
            <HStack justify="space-between" align="center">
              <Text textStyle="t2Medium" color="fg.neutralSubtle">
                점검 대상
              </Text>
              <Icon svg={<IconChevronDownLine />} size="x3_5" color="fg.neutralSubtle" />
            </HStack>
            <HStack gap="x1_5" align="center" justify="space-between">
              <Text textStyle="t4Bold" color="fg.neutral" maxLines={1}>
                {domain.domain}
              </Text>
              {domain.verify_status === 'verified' && (
                <Badge tone="positive" variant="weak" size="medium">
                  확인됨
                </Badge>
              )}
            </HStack>
          </VStack>
        </MenuTrigger>
        <MenuContent>
          {domains.length > 1 && (
            <MenuGroup>
              {domains.map((d) => (
                <MenuItem
                  key={d.domain_id}
                  label={d.domain_id === domain.domain_id ? `${d.domain} (지금)` : d.domain}
                  disabled={d.domain_id === domain.domain_id}
                  onClick={() => {
                    select(d.domain_id)
                    navigate('/dashboard')
                  }}
                />
              ))}
            </MenuGroup>
          )}
          <MenuGroup>
            <MenuItem label="도메인 추가" prefixIcon={<IconPlusLine />} onClick={() => navigate('/register')} />
          </MenuGroup>
        </MenuContent>
      </MenuRoot>
    </Box>
  )
}

function UserMenu() {
  const { collapsed } = useSideNavigationContext()
  const navigate = useNavigate()
  const { data } = useApi(() => api.auth.me(), [])

  const logout = async () => {
    await api.auth.logout().catch(() => undefined)
    navigate('/login')
  }

  return (
    <MenuRoot>
      <MenuTrigger asChild>
        <HStack as="button" align="center" gap="x3" width="full" p="x2" borderRadius="r3" style={{ cursor: 'pointer', background: 'none', border: 0 }}>
          <Avatar size="36" fallback={<IdentityPlaceholder />} />
          {!collapsed && (
            <VStack gap="x0_5" align="flex-start">
              <Text textStyle="t4Medium" color="fg.neutral" maxLines={1}>
                {data?.user.name ?? '…'}
              </Text>
              <Text textStyle="t2Regular" color="fg.neutralSubtle" maxLines={1}>
                {data?.user.email ?? ''}
              </Text>
            </VStack>
          )}
        </HStack>
      </MenuTrigger>
      <MenuContent>
        <MenuGroup>
          <MenuItem label="로그아웃" prefixIcon={<IconArrowLeftBracketRightLine />} onClick={logout} />
        </MenuGroup>
      </MenuContent>
    </MenuRoot>
  )
}

// 현재 도메인을 먼저 정하고(DomainProvider), 그 도메인의 점검 상태를 나눠 쓴다(ScanProvider).
// 도메인이 없으면 DomainProvider가 등록 화면으로 보낸다.
export function AppShell() {
  return (
    <DomainProvider>
      <Shell />
    </DomainProvider>
  )
}

function Shell() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { domain } = useDomain()

  // 도메인을 바꾸면 key가 바뀌어 점검 상태도 새로 시작한다.
  return (
    <ScanProvider key={domain.domain_id} domainId={domain.domain_id}>
    <Layout.Root>
      <SideNavigationProvider>
        <SideNavigationRoot>
          <SideNavigationHeader>
            <HStack justify="space-between" align="center" width="full">
              <Brand />
              <SideNavigationTrigger />
            </HStack>
          </SideNavigationHeader>

          <SideNavigationContent>
            <DomainChip />
            <SideNavigationGroup
              items={NAV.map((item) => ({
                key: item.path,
                label: item.label,
                prefixIcon: item.icon,
                current: pathname.startsWith(item.path),
                onClick: () => navigate(item.path),
              }))}
            />
          </SideNavigationContent>

          <SideNavigationFooter>
            <UserMenu />
          </SideNavigationFooter>
        </SideNavigationRoot>

        <SideNavigationInset>
          <div className="a2d-flow-line" aria-hidden="true" />
          <Layout.Content>
            <Box px="spacingX.globalGutter" py="x8">
              <VStack gap="x6">
                <ScanBanner />
                <PageTransition>
                  <Outlet />
                </PageTransition>
              </VStack>
            </Box>
          </Layout.Content>
        </SideNavigationInset>
      </SideNavigationProvider>
    </Layout.Root>
    </ScanProvider>
  )
}
