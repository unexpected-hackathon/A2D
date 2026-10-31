// 내용 영역의 바탕색. 고른 종이가 바뀌면 새 색이 물결 모양 앞머리로 왼쪽에서 오른쪽으로 쓸고 지나간다.
//
// 흐름
//   shown  = 지금 깔려 있는 색 (바탕 div)
//   fill   = 고른 종이의 색. shown과 다르면 "들어오는 색"이다
//   들어오는 색은 겹친 overlay(SVG, 오른쪽 끝이 물결)로 그리고, motion으로 x를 -104% → 0 으로 움직인다
//   다 지나가면(onAnimationComplete) shown을 새 색으로 바꾸고 overlay를 치운다
// 움직임 줄이기 설정이면 바로 바꾼다.

import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'

const W = 1000
const H = 1000
const EDGE = 950 // 물결의 평균 위치 (0~1000)
const AMP = 28

// 오른쪽 끝이 물결인 직사각형. phase를 바꾸면 물결이 흔들린다.
function washPath(phase: number) {
  const pts: string[] = []
  const n = 24
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const x = EDGE + AMP * Math.sin(t * Math.PI * 3 + phase)
    pts.push(`L${x.toFixed(1)},${(t * H).toFixed(1)}`)
  }
  return `M0,0 L${EDGE},0 ${pts.join(' ')} L0,${H} Z`
}
const D0 = washPath(0)
const D1 = washPath(Math.PI)

interface SheetWashProps {
  id: string // 종이 키. 바뀌면 쓸고 지나간다
  fill: string
}

export function SheetWash({ id, fill }: SheetWashProps) {
  const reduce = useReducedMotion()
  const [shown, setShown] = useState({ id, fill })
  const incoming = shown.id !== id ? { id, fill } : null

  return (
    <>
      <div className="a2d-sheet__bg" style={{ background: shown.fill }} aria-hidden="true" />
      <AnimatePresence>
        {incoming && (
          <motion.div
            key={incoming.id}
            className="a2d-sheet__wash"
            aria-hidden="true"
            initial={{ x: reduce ? '0%' : '-104%' }}
            animate={{ x: '0%' }}
            transition={{ duration: reduce ? 0 : 0.6, ease: [0.3, 0.9, 0.35, 1] }}
            onAnimationComplete={() => setShown(incoming)}
          >
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
              <path d={D0} fill={incoming.fill}>
                {!reduce && <animate attributeName="d" values={`${D0};${D1};${D0}`} dur="0.6s" repeatCount="1" />}
              </path>
            </svg>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
