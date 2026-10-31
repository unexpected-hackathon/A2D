// 내용 영역의 바탕색. 고른 종이가 바뀌면 새 색이 물결 모양 앞머리로 왼쪽에서 오른쪽으로 쓸고 지나간다.
//
// 흐름
//   shown  = 지금 깔려 있는 색 (바탕 div)
//   fill   = 고른 종이의 색. shown과 다르면 "들어오는 색"이다
//   들어오는 색은 겹친 overlay(SVG, 오른쪽 끝이 물결)로 그리고, motion으로 x를 -112% → 0 으로 움직인다
//   앞머리가 내용 영역의 왼쪽 40%쯤을 덮으면 onCover를 한 번 부른다 → AppShell이 제목 글자색을 새 종이 색에 맞춘다
//   다 지나가면(onAnimationComplete) shown을 새 색으로 바꾸고 overlay를 치운다
// 움직임 줄이기 설정이면 바로 바꾼다.
//
// 치수: overlay 폭은 내용 영역의 112%. 물결 앞머리는 overlay 안에서 (EDGE±AMP)/W = 91.6~98.4% 자리에 있어,
// x=0에 닿았을 때 앞머리의 가장 뒤처진 골도 내용 영역의 102.6% 지점(오른쪽 밖)에 있다.
// 그래야 다 지나갔을 때 오른쪽에 이전 색 띠가 남지 않는다.

import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useRef, useState } from 'react'

const W = 1000
const H = 1000
const EDGE = 950 // 물결의 평균 위치 (0~1000)
const AMP = 34 // 물결 높이. 클수록 앞머리가 또렷하게 굽이친다
const WIDTH = 112 // overlay 폭 (내용 영역 폭의 %)
// 앞머리 중 가장 앞선 마루가 내용 영역의 40%를 지나는 x(%). 이때 왼쪽의 제목 글자는 새 색 위에 있다.
const COVER_AT = 40 - ((EDGE + AMP) / W) * WIDTH

// 오른쪽 끝이 물결인 직사각형. phase를 바꾸면 물결이 흔들린다.
function washPath(phase: number) {
  const pts: string[] = []
  const n = 24
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const x = EDGE + AMP * Math.sin(t * Math.PI * 1.8 + phase)
    pts.push(`L${x.toFixed(1)},${(t * H).toFixed(1)}`)
  }
  return `M0,0 L${EDGE},0 ${pts.join(' ')} L0,${H} Z`
}
// 지나가는 동안 물결이 두 번 흔들리도록 모양 셋을 번갈아 보여 준다
const D0 = washPath(0)
const D1 = washPath(Math.PI)
const DUR = 1.1 // 쓸고 지나가는 시간(초)

interface SheetWashProps {
  id: string // 종이 키. 바뀌면 쓸고 지나간다
  fill: string
  onCover?: () => void // 새 색이 왼쪽 제목 자리를 덮었을 때 (종이마다 한 번)
}

export function SheetWash({ id, fill, onCover }: SheetWashProps) {
  const reduce = useReducedMotion()
  const [shown, setShown] = useState({ id, fill })
  const incoming = shown.id !== id ? { id, fill } : null
  const covered = useRef<string | null>(null)

  const cover = (key: string) => {
    if (covered.current === key) return
    covered.current = key
    onCover?.()
  }

  return (
    <>
      <div className="a2d-sheet__bg" style={{ background: shown.fill }} aria-hidden="true" />
      <AnimatePresence>
        {incoming && (
          <motion.div
            key={incoming.id}
            className="a2d-sheet__wash"
            aria-hidden="true"
            initial={{ x: reduce ? '0%' : `-${WIDTH}%` }}
            animate={{ x: '0%' }}
            transition={{ duration: reduce ? 0 : DUR, ease: [0.25, 0.7, 0.3, 1] }}
            onUpdate={(latest) => {
              if (parseFloat(String(latest.x)) >= COVER_AT) cover(incoming.id)
            }}
            onAnimationComplete={() => {
              cover(incoming.id)
              setShown(incoming)
            }}
          >
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
              <path d={D0} fill={incoming.fill}>
                {!reduce && (
                  <animate attributeName="d" values={`${D0};${D1};${D0};${D1};${D0}`} dur={`${DUR}s`} repeatCount="1" />
                )}
              </path>
            </svg>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
