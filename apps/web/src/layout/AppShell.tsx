// 로그인·등록을 뺀 모든 화면의 공통 틀 (정보 구조도 2장).
// 왼쪽: SEED SideNavigation (로고, 메뉴 3개, 사용자 메뉴)
// 오른쪽: 맨 위 브랜드 줄 + 지금 주소의 화면(<Outlet />)

import {
  IconArrowLeftBracketRightLine,
  IconCheckmarkShieldFill,
  IconClockFill,
  IconHouseFill,
} from '@karrotmarket/react-monochrome-icon'
import { Box, HStack, Layout, Text, VStack, useSideNavigationContext } from '@seed-design/react'
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
import { getCurrentDomainId } from '../api/currentDomain'
import { useApi } from '../hooks/useApi'
import logoUrl from '../assets/a2d-logo.svg'
import iconUrl from '../assets/a2d-icon.svg'
import { ScanProvider } from '../hooks/ScanProvider'
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

function DomainChip() {
  const { collapsed } = useSideNavigationContext()
  const domainId = getCurrentDomainId()
  const { data } = useApi(() => (domainId ? api.domains.get(domainId) : Promise.resolve(undefined)), [domainId])
  if (collapsed || !data) return null
  return (
    <Box px="x2" pb="x2">
      <VStack gap="x1" p="x3" borderRadius="r3" bg="bg.neutralWeak">
        <Text textStyle="t2Medium" color="fg.neutralSubtle">
          점검 대상
        </Text>
        <HStack gap="x1_5" align="center" justify="space-between">
          <Text textStyle="t4Bold" color="fg.neutral" maxLines={1}>
            {data.domain}
          </Text>
          {data.verify_status === 'verified' && (
            <Badge tone="positive" variant="weak" size="medium">
              확인됨
            </Badge>
          )}
        </HStack>
      </VStack>
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

export function AppShell() {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // 점검 상태는 여기서 한 번만 관리하고, 진행 띠와 화면들이 useScan()으로 나눠 쓴다.
  return (
    <ScanProvider domainId={getCurrentDomainId()}>
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
