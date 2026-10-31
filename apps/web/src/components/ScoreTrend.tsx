// 4-1 안전 점수 추이 그래프. SEED에 그래프가 없어 SVG로 직접 그린다(라이브러리 없음).
// 세로축 0~100, 뒤에 등급 구간(A 90+ / B 72+ / C 58+ / D 44+ / F) 띠를 깔고,
// 점검마다 점을 찍어 선으로 잇는다. 점을 누르면 그 점검을 고른다.

import { motion, useReducedMotion } from 'motion/react'
import type { HistoryItem } from '../api/types'

const W = 720
const H = 260
const PAD = { top: 16, right: 24, bottom: 36, left: 40 }
const BANDS = [
  { grade: 'A', from: 90, to: 100, color: 'var(--seed-color-bg-positive-weak)' },
  { grade: 'B', from: 72, to: 90, color: 'var(--seed-color-bg-positive-weak)' },
  { grade: 'C', from: 58, to: 72, color: 'var(--seed-color-bg-informative-weak)' },
  { grade: 'D', from: 44, to: 58, color: 'var(--seed-color-bg-warning-weak)' },
  { grade: 'F', from: 0, to: 44, color: 'var(--seed-color-bg-critical-weak)' },
]

interface ScoreTrendProps {
  items: HistoryItem[]
  selectedScanId: string | null
  onSelect: (scanId: string) => void
}

export function ScoreTrend({ items, selectedScanId, onSelect }: ScoreTrendProps) {
  const reduce = useReducedMotion()
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const y = (score: number) => PAD.top + innerH * (1 - score / 100)
  // 점이 하나뿐이면 가운데에 둔다.
  const x = (i: number) => PAD.left + (items.length === 1 ? innerW / 2 : (innerW * i) / (items.length - 1))
  const path = items.map((it, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(it.safety_score)}`).join(' ')

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', minWidth: 360, height: 'auto', display: 'block' }}
        role="img"
        aria-label={`안전 점수 추이: ${items.map((it) => `${it.scan_id} ${it.safety_score}점`).join(', ')}`}
      >
        {/* 등급 구간 띠와 왼쪽 등급 글자 */}
        {BANDS.map((b) => (
          <g key={b.grade}>
            <rect x={PAD.left} y={y(b.to)} width={innerW} height={y(b.from) - y(b.to)} fill={b.color} opacity={0.6} />
            <text x={PAD.left - 10} y={(y(b.to) + y(b.from)) / 2 + 4} textAnchor="end" fontSize="12" fontWeight="700" fill="var(--seed-color-fg-neutral-subtle)">
              {b.grade}
            </text>
          </g>
        ))}

        {/* 점수 선: 왼쪽부터 그려지며 나타난다 */}
        {items.length > 1 && (
          <motion.path
            d={path}
            fill="none"
            stroke="var(--seed-color-bg-brand-solid)"
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
            initial={reduce ? false : { pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.9, ease: 'easeInOut' }}
          />
        )}

        {/* 점과 점수, 아래 점검 ID */}
        {items.map((it, i) => {
          const selected = it.scan_id === selectedScanId
          return (
            <g key={it.scan_id} onClick={() => onSelect(it.scan_id)} style={{ cursor: 'pointer' }}>
              <circle cx={x(i)} cy={y(it.safety_score)} r={16} fill="transparent" />
              <circle
                cx={x(i)}
                cy={y(it.safety_score)}
                r={selected ? 7 : 5}
                fill={selected ? 'var(--seed-color-bg-brand-solid)' : 'var(--seed-color-bg-layer-default)'}
                stroke="var(--seed-color-bg-brand-solid)"
                strokeWidth={3}
              />
              <text x={x(i)} y={y(it.safety_score) - 14} textAnchor="middle" fontSize="13" fontWeight="700" fill="var(--seed-color-fg-neutral)">
                {`${it.safety_score} ${it.grade}`}
              </text>
              <text x={x(i)} y={H - 12} textAnchor="middle" fontSize="11" fill="var(--seed-color-fg-neutral-subtle)">
                {it.scan_id}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
