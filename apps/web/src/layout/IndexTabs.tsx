// 파일 색인 탭 (메뉴). 폴더 가장자리에 탭 세 개가 계단식으로 튀어나와 있다.
// 왼쪽부터(위부터) 주황=대시보드, 흰색=조치 가이드, 갈색=기록.
//
//   - 선택한 탭: 앞으로 나와 더 길게 튀어나오고, 내용 영역과 같은 색으로 이어진다(z-index가 내용 영역보다 위).
//   - 나머지 탭: 뒤에 끼워진 칸막이처럼 한 단계 안쪽에, 내용 영역 뒤에 그린다.
//   - 탭 위치는 CSS 변수(--i)로 장마다 한 칸씩 내린다(가로 띠에서는 오른쪽으로 민다).
//
// orientation
//   - vertical:   넓은 화면. 내용 영역 왼쪽 가장자리에 세로로.
//   - horizontal: 휴대폰. 내용 영역 위쪽 가장자리에 가로로.

import type { CSSProperties, ReactNode } from 'react'

export interface IndexTab {
  key: string
  label: string
  icon: ReactNode
  fill: string // 탭 색
  ink: string // 탭 위 글자 색
}

interface IndexTabsProps {
  tabs: IndexTab[]
  activeKey: string | null
  orientation: 'vertical' | 'horizontal'
  onSelect: (key: string) => void
}

export function IndexTabs({ tabs, activeKey, orientation, onSelect }: IndexTabsProps) {
  const horizontal = orientation === 'horizontal'
  return (
    <nav className={`a2d-tabs a2d-tabs--${orientation}`} aria-label="화면 이동">
      {tabs.map((tab, i) => {
        const active = tab.key === activeKey
        return (
          <button
            key={tab.key}
            type="button"
            className="a2d-tab"
            data-active={active}
            aria-current={active ? 'page' : undefined}
            onClick={() => onSelect(tab.key)}
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
