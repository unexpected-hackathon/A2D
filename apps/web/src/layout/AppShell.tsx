// 로그인·등록을 뺀 모든 화면의 공통 틀 (정보 구조도 2장).
//
//   ┌ 머리글(위에 고정) ─────────────────────────────────────┐
//   │ 로고  [점검 대상 도메인 ▾]                    [사용자 ▾] │
//   └───────────────────────────────────────────────────────┘
//   ▟주황▙▟흰색▙▟갈색▙
//   ┌ 내용 영역(큰 카드) ────────────────────────────────────┐
//   │  지금 주소의 화면(<Outlet />)                           │
//   │  바탕은 고른 탭과 같은 색(물결로 쓸고 지나가며 바뀜)     │
//   └───────────────────────────────────────────────────────┘
//   카드 왼쪽 위에 붙은 파일 색인 탭 세 개(IndexTabs)가 메뉴다.

import {
  IconArrowLeftBracketRightLine,
  IconCheckmarkShieldFill,
  IconChevronDownLine,
  IconClockFill,
  IconHouseFill,
  IconPlusLine,
} from '@karrotmarket/react-monochrome-icon'
import { HStack, Icon, Text, VStack } from '@seed-design/react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Outlet, useLocation, useNavigate, useNavigationType } from 'react-router-dom'
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
import { IndexTabs, type IndexTab } from './IndexTabs'
import { ScanBanner } from './ScanBanner'
import { SheetWash } from './SheetWash'

// 탭 세 개: 위(왼쪽)부터 주황·흰색·갈색. 색은 global.css의 --a2d-paper-* 변수.
const PAPERS: IndexTab[] = [
  { key: 'dashboard', path: '/dashboard', label: '대시보드', icon: <IconHouseFill />, fill: 'var(--a2d-paper-orange)', ink: '#ffffff' },
  { key: 'guide', path: '/guide', label: '조치 가이드', icon: <IconCheckmarkShieldFill />, fill: 'var(--a2d-paper-white)', ink: 'var(--a2d-navy)' },
  { key: 'history', path: '/history', label: '기록', icon: <IconClockFill />, fill: 'var(--a2d-paper-brown)', ink: '#ffffff' },
]
// 어느 탭에도 맞지 않는 주소(/dev/api 등)일 때의 바탕: 아무 탭도 고르지 않고 중립색 종이를 깐다.
const NEUTRAL = { key: 'none', fill: 'var(--a2d-sheet)', ink: 'var(--a2d-navy)' }

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
  const { pathname, hash } = useLocation()
  const navType = useNavigationType()
  const { domain } = useDomain()
  const tab = PAPERS.find((p) => pathname.startsWith(p.path))
  const paper = tab ?? NEUTRAL

  // 제목 글자색. 바탕은 물결이 쓸고 지나가며 늦게 바뀌므로, 글자색은 SheetWash가 바탕에 맞춰 알려 주는 값을 쓴다.
  const [ink, setInk] = useState(paper.ink)

  // 다른 탭으로 넘어가면 맨 위에서 시작한다. 같은 탭 안의 이동(/guide → /guide/:scanId), 뒤로가기(브라우저가
  // 스크롤 위치를 되돌린다), #task-N처럼 위치를 정해 온 경우는 그대로 둔다.
  const prevPaper = useRef(paper.key)
  useEffect(() => {
    const changed = prevPaper.current !== paper.key
    prevPaper.current = paper.key
    if (changed && navType !== 'POP' && !hash) window.scrollTo({ top: 0 })
  }, [paper.key, navType, hash])

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

        <div className="a2d-folder">
          <IndexTabs tabs={PAPERS} activeKey={tab?.key ?? null} onSelect={(t) => navigate(t.path)} />
          {/* 내용 영역: 바탕은 고른 종이 색(SheetWash), 글자색은 그 종이의 ink */}
          <main className="a2d-sheet" data-paper={paper.key} style={{ '--a2d-ink': ink } as CSSProperties}>
            <SheetWash paper={{ id: paper.key, fill: paper.fill, ink: paper.ink }} onInk={setInk} />
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
