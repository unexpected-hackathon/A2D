// 로그인·등록을 뺀 모든 화면의 공통 틀 (정보 구조도 2장).
//
//   ┌ 머리글(위에 고정) ─────────────────────────────────────┐
//   │ 로고  [점검 대상 도메인 ▾]                    [사용자 ▾] │
//   └───────────────────────────────────────────────────────┘
//   ┌ 큰 카드 ──────────────────────────────────────────────┐
//   │ 주황│흰색│갈색 ≈≈ │  지금 주소의 화면(<Outlet />)         │
//   │    (계단식 탭)    │  바탕은 고른 종이와 같은 색(물결로 바뀜) │
//   │ 대시│조치│기록 ≈≈ │                                       │
//   └───────────────────────────────────────────────────────┘
//   겹친 종이 세 장(PaperTabs)이 메뉴다. 휴대폰에서는 종이가 카드 위쪽에 가로로 겹친다.

import {
  IconArrowLeftBracketRightLine,
  IconCheckmarkShieldFill,
  IconChevronDownLine,
  IconClockFill,
  IconHouseFill,
  IconPlusLine,
} from '@karrotmarket/react-monochrome-icon'
import { HStack, Icon, Text, VStack, useBreakpointValue } from '@seed-design/react'
import { useEffect, type CSSProperties } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Avatar } from 'seed-design/ui/avatar'
import { Badge } from 'seed-design/ui/badge'
import { IdentityPlaceholder } from 'seed-design/ui/identity-placeholder'
import { MenuContent, MenuGroup, MenuItem, MenuRoot, MenuTrigger } from 'seed-design/ui/menu'
import { api } from '../api/endpoints'
import iconUrl from '../assets/a2d-icon.svg'
import logoUrl from '../assets/a2d-logo.svg'
import { DomainProvider } from '../hooks/DomainProvider'
import { ScanProvider } from '../hooks/ScanProvider'
import { useApi } from '../hooks/useApi'
import { useDomain } from '../hooks/useDomain'
import { PageTransition } from './PageTransition'
import { PaperTabs, type PaperTab } from './PaperTabs'
import { ScanBanner } from './ScanBanner'
import { SheetWash } from './SheetWash'

// 종이 세 장: 왼쪽(위)부터 주황·흰색·갈색. 색은 global.css의 --a2d-paper-* 변수.
const PAPERS: (PaperTab & { path: string })[] = [
  { key: 'dashboard', path: '/dashboard', label: '대시보드', icon: <IconHouseFill />, fill: 'var(--a2d-paper-orange)', ink: '#ffffff' },
  { key: 'guide', path: '/guide', label: '조치 가이드', icon: <IconCheckmarkShieldFill />, fill: 'var(--a2d-paper-white)', ink: 'var(--a2d-navy)' },
  { key: 'history', path: '/history', label: '기록', icon: <IconClockFill />, fill: 'var(--a2d-paper-brown)', ink: '#ffffff' },
]

// 점검 대상 도메인. 누르면 다른 도메인으로 바꾸거나 새 도메인을 추가한다.
function DomainSwitcher() {
  const { domain, domains, select } = useDomain()
  const navigate = useNavigate()
  return (
    <MenuRoot>
      <MenuTrigger asChild>
        <button type="button" className="a2d-domain" aria-label={`점검 대상 ${domain.domain}, 바꾸거나 추가하기`}>
          <VStack gap="x0_5" align="flex-start" className="a2d-min0">
            <Text textStyle="t2Medium" color="fg.neutralSubtle">
              점검 대상
            </Text>
            <HStack gap="x1_5" align="center">
              <Text textStyle="t4Bold" color="fg.neutral" maxLines={1}>
                {domain.domain}
              </Text>
              {domain.verify_status === 'verified' && (
                <Badge tone="positive" variant="weak" size="medium" className="a2d-keep">
                  확인됨
                </Badge>
              )}
            </HStack>
          </VStack>
          <Icon svg={<IconChevronDownLine />} size="x4" color="fg.neutralSubtle" />
        </button>
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
  )
}

function UserMenu() {
  const navigate = useNavigate()
  const { data } = useApi(() => api.auth.me(), [])

  const logout = async () => {
    await api.auth.logout().catch(() => undefined)
    navigate('/login')
  }

  return (
    <MenuRoot>
      <MenuTrigger asChild>
        <button type="button" className="a2d-user" aria-label={`사용자 메뉴 ${data?.user.name ?? ''}`}>
          <Avatar size="36" fallback={<IdentityPlaceholder />} />
          <VStack gap="x0_5" align="flex-start" className="a2d-user__text">
            <Text textStyle="t4Medium" color="fg.neutral" maxLines={1}>
              {data?.user.name ?? '…'}
            </Text>
            <Text textStyle="t2Regular" color="fg.neutralSubtle" maxLines={1}>
              {data?.user.email ?? ''}
            </Text>
          </VStack>
        </button>
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
  // 768px 미만(휴대폰)에서는 종이를 위쪽에 가로로 겹친다.
  const horizontal = useBreakpointValue({ base: true, md: false }) ?? false
  const { hash } = useLocation()
  const paper = PAPERS.find((p) => pathname.startsWith(p.path)) ?? PAPERS[0]
  const active = paper.key

  // 다른 종이로 넘어가면 맨 위에서 시작한다(#task-N처럼 위치를 정해 온 경우는 그대로 둔다).
  useEffect(() => {
    if (!hash) window.scrollTo({ top: 0 })
  }, [pathname, hash])

  // 도메인을 바꾸면 key가 바뀌어 점검 상태도 새로 시작한다.
  return (
    <ScanProvider key={domain.domain_id} domainId={domain.domain_id}>
      <div className="a2d-app">
        <header className="a2d-header">
          <HStack gap="x4" align="center" className="a2d-min0">
            <button type="button" className="a2d-brand" onClick={() => navigate('/dashboard')} aria-label="A2D 대시보드">
              <img src={logoUrl} alt="" height={30} className="a2d-brand__logo" />
              <img src={iconUrl} alt="" width={30} height={30} className="a2d-brand__icon" />
            </button>
            <DomainSwitcher />
          </HStack>
          <UserMenu />
        </header>

        <div
          className="a2d-folder"
          data-orientation={horizontal ? 'horizontal' : 'vertical'}
          style={{ '--a2d-folder-bg': paper.fill } as CSSProperties}
        >
          <PaperTabs
            tabs={PAPERS}
            activeKey={active}
            orientation={horizontal ? 'horizontal' : 'vertical'}
            onSelect={(key) => navigate(PAPERS.find((p) => p.key === key)!.path)}
          />
          {/* 내용 영역: 바탕은 고른 종이 색(SheetWash), 글자색은 그 종이의 ink */}
          <main className="a2d-sheet" data-paper={active} style={{ '--a2d-ink': paper.ink } as CSSProperties}>
            <SheetWash id={paper.key} fill={paper.fill} />
            <div className="a2d-sheet__content">
              <VStack gap="x6">
                <ScanBanner />
                <PageTransition>
                  <Outlet />
                </PageTransition>
              </VStack>
            </div>
          </main>
        </div>
      </div>
    </ScanProvider>
  )
}
