// 파일 색인 탭 (메뉴). 내용 영역 위쪽 가장자리의 왼쪽에 탭이 가로로 나란히 붙어 있다.
// 왼쪽부터 주황=대시보드, 흰색=조치 가이드, 갈색=기록.
//
//   - 선택한 탭: 조금 더 크고 앞으로 나오며, 내용 영역 위로 8px 겹쳐 같은 색으로 이어진다.
//   - 나머지 탭: 한 단계 낮게, 내용 영역 가장자리까지만 온다. 앞 탭이 뒤 탭 위에 놓인다(--i로 순서).
//   - 탭 폭은 글자 길이대로. 휴대폰에서는 선택한 탭이 남는 폭을 채운다.
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
  onSelect: (tab: IndexTab) => void
}

export function IndexTabs({ tabs, activeKey, onSelect }: IndexTabsProps) {
  return (
    <nav className="a2d-tabs" aria-label="화면 이동">
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
            <span className="a2d-tab__label">{tab.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
