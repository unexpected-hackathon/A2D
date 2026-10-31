// 파일 색인 탭 (메뉴). 폴더 가장자리에 탭이 계단식으로 튀어나와 있다.
// 위(왼쪽)부터 주황=대시보드, 흰색=조치 가이드, 갈색=기록.
//
//   - 선택한 탭: 앞으로 나와 더 길게 튀어나오고, 내용 영역 위로 8px 겹쳐 같은 색으로 이어진다.
//   - 나머지 탭: 한 단계 안쪽에, 내용 영역 가장자리까지만 온다(겹치지 않는다).
//   - 탭 위치는 CSS 변수로 정한다. --i는 몇 번째 탭인지, --n은 탭 수(세로 띠의 높이 계산).
//
// orientation
//   - vertical:   넓은 화면. 내용 영역 왼쪽 가장자리에 세로로.
//   - horizontal: 휴대폰. 내용 영역 위쪽 가장자리에 가로로. 폭은 글자 길이대로, 선택한 탭이 남는 폭을 채운다.
//
// 이 컴포넌트는 그리기만 한다. 어디로 갈지는 onSelect로 받은 탭의 path를 보고 AppShell이 정한다.

import type { CSSProperties, ReactNode } from 'react'

export interface IndexTab {
  key: string
  path: string
  label: string
  icon: ReactNode
  fill: string // 탭 색
  ink: string // 탭 위 글자 색
}

interface IndexTabsProps {
  tabs: IndexTab[]
  activeKey: string | null // 어느 탭에도 맞지 않는 주소면 null (아무 탭도 고르지 않은 상태)
  orientation: 'vertical' | 'horizontal'
  onSelect: (tab: IndexTab) => void
}

export function IndexTabs({ tabs, activeKey, orientation, onSelect }: IndexTabsProps) {
  const horizontal = orientation === 'horizontal'
  return (
    <nav
      className={`a2d-tabs a2d-tabs--${orientation}`}
      aria-label="화면 이동"
      style={{ '--n': tabs.length } as CSSProperties}
    >
      {tabs.map((tab, i) => {
        const active = tab.key === activeKey
        return (
          <button
            key={tab.key}
            type="button"
            className="a2d-tab"
            data-active={active}
            aria-current={active ? 'page' : undefined}
            onClick={() => onSelect(tab)}
            style={{ '--i': i, '--tab-fill': tab.fill, color: tab.ink } as CSSProperties}
          >
            <span className="a2d-tab__icon">{tab.icon}</span>
            {/* 세로 글자에서는 띄어쓰기가 빈칸으로 보여 붙여 쓴다 */}
            <span className="a2d-tab__label">{horizontal ? tab.label : tab.label.replaceAll(' ', '')}</span>
          </button>
        )
      })}
    </nav>
  )
}
