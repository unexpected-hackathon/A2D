// 겹쳐 놓은 종이 세 장 (메뉴). 왼쪽부터 주황=대시보드, 흰색=조치 가이드, 갈색=기록.
//
// 그리는 방법
//   - SVG 하나에 종이 세 장을 겹쳐 그린다. 가장 긴(오른쪽) 종이부터 그리고 짧은 종이를 위에 올린다.
//   - 종이 끝(경계)은 물결선이고, 두 물결 모양을 번갈아 보여 주며 천천히 출렁인다(SVG <animate>).
//   - 띠 한 칸의 폭은 CSS 변수(--a2d-paper)로 정하고, SVG는 viewBox 단위(한 칸=100)로 그려
//     preserveAspectRatio="none"으로 늘인다. 그래서 화면 크기가 바뀌어도 모양이 같다.
//   - 누르는 영역은 SVG 위에 겹친 버튼 세 개다(접근성: 버튼 이름 = 화면 이름).
//
// orientation
//   - vertical:   넓은 화면. 종이가 왼쪽에 세로로 겹친다(오른쪽 끝이 물결).
//   - horizontal: 휴대폰. 종이가 위쪽에 가로로 겹친다(아래 끝이 물결).

import { useReducedMotion } from 'motion/react'
import type { CSSProperties, ReactNode } from 'react'

export interface PaperTab {
  key: string
  label: string
  icon: ReactNode
  fill: string // 종이 색
  ink: string // 종이 위 글자 색
}

interface PaperTabsProps {
  tabs: PaperTab[]
  activeKey: string | null
  orientation: 'vertical' | 'horizontal'
  onSelect: (key: string) => void
}

const UNIT = 100 // 종이 한 칸의 폭(viewBox 단위)
const LENGTH = 1000 // 종이 길이(viewBox 단위)
const AMP = 7 // 물결 높이
const SAMPLES = 32

// 경계선 위의 점들. phase를 바꾸면 물결이 옆으로 흐르는 것처럼 보인다.
function wave(edge: number, phase: number, i: number) {
  const pts: [number, number][] = []
  for (let s = 0; s <= SAMPLES; s++) {
    const t = s / SAMPLES
    // 굽이 하나짜리 완만한 곡선. 종이마다 위상을 달리해 서로 다른 모양으로 보인다.
    const offset = AMP * Math.sin(t * Math.PI * 1.15 + phase + i * 1.1)
    pts.push([edge + offset, t * LENGTH])
  }
  return pts
}

// 종이 하나의 모양: 시작 변(0)에서 물결 경계까지 채운 면.
function paperPath(edge: number, phase: number, i: number, horizontal: boolean) {
  const pts = wave(edge, phase, i).map(([a, b]) => (horizontal ? [b, a] : [a, b]))
  const head = horizontal ? 'M0,0 L0,' : 'M0,0 L'
  const start = horizontal ? `${head}${pts[0][1].toFixed(1)}` : `${head}${pts[0][0].toFixed(1)},0`
  const line = pts.map(([x, y]) => `L${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const close = horizontal ? `L${LENGTH},0 Z` : `L0,${LENGTH} Z`
  return `${start} ${line} ${close}`
}

export function PaperTabs({ tabs, activeKey, orientation, onSelect }: PaperTabsProps) {
  const reduce = useReducedMotion()
  const horizontal = orientation === 'horizontal'
  const span = tabs.length * UNIT
  const viewBox = horizontal ? `0 0 ${LENGTH} ${span}` : `0 0 ${span} ${LENGTH}`

  return (
    <div className={`a2d-papers a2d-papers--${orientation}`}>
      <svg className="a2d-papers__art" viewBox={viewBox} preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <filter id="a2d-paper-shadow" x="-10%" y="-10%" width="130%" height="130%">
            <feDropShadow dx={horizontal ? 0 : 2} dy={horizontal ? 2 : 0} stdDeviation="2.5" floodColor="#10202f" floodOpacity="0.16" />
          </filter>
        </defs>
        {/* 오른쪽(아래) 종이부터 그려야 왼쪽(위) 종이가 위에 겹친다 */}
        {[...tabs.keys()].reverse().map((i) => {
          // 마지막 종이 끝은 칸 안에 머물도록 물결 높이만큼 안쪽으로
          const edge = (i + 1) * UNIT - (i === tabs.length - 1 ? AMP + 2 : 0)
          const d0 = paperPath(edge, 0, i, horizontal)
          const d1 = paperPath(edge, Math.PI, i, horizontal)
          return (
            <path key={tabs[i].key} d={d0} fill={tabs[i].fill} filter="url(#a2d-paper-shadow)">
              {!reduce && (
                <animate
                  attributeName="d"
                  values={`${d0};${d1};${d0}`}
                  dur={`${9 + i * 2}s`}
                  repeatCount="indefinite"
                  calcMode="spline"
                  keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                />
              )}
            </path>
          )
        })}
      </svg>

      {/* 누르는 영역: 종이 한 장당 버튼 하나 */}
      <nav className="a2d-papers__buttons" aria-label="화면 이동">
        {tabs.map((tab, i) => {
          const active = tab.key === activeKey
          return (
            <button
              key={tab.key}
              type="button"
              className="a2d-papers__tab"
              data-active={active}
              aria-current={active ? 'page' : undefined}
              onClick={() => onSelect(tab.key)}
              // --i: 파일 색인 탭처럼 장마다 글자 위치를 한 칸씩 내린다(CSS)
              style={{ color: tab.ink, '--i': i } as CSSProperties}
            >
              {/* 스크롤해도 글자가 화면 위쪽에 남도록 한 겹 감싼다(sticky) */}
              <span className="a2d-papers__face">
                <span className="a2d-papers__icon">{tab.icon}</span>
                {/* 세로 글자에서는 띄어쓰기가 빈칸으로 보여 붙여 쓴다 */}
                <span className="a2d-papers__label">{horizontal ? tab.label : tab.label.replaceAll(' ', '')}</span>
              </span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
