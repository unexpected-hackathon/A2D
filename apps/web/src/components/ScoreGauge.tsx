// 안전 점수 게이지. 0~100 가로 막대에 등급 구간 띠를 깔고, 현재 점수 자리에 점을 찍는다.
// 막대 그래프보다 "100점 중 어디쯤인지"가 바로 보이게 한 장 요약에서 쓴다.

import type { Grade } from '../api/types'
import { gradeStyle } from '../theme/severity'

// 등급 구간(ScoreTrend와 같은 기준: A 90+ / B 72+ / C 58+ / D 44+ / F)
const BANDS: { grade: Grade; from: number; to: number }[] = [
  { grade: 'F', from: 0, to: 44 },
  { grade: 'D', from: 44, to: 58 },
  { grade: 'C', from: 58, to: 72 },
  { grade: 'B', from: 72, to: 90 },
  { grade: 'A', from: 90, to: 100 },
]
const TICKS = [0, 44, 58, 72, 90, 100]

export function ScoreGauge({ score, grade }: { score: number; grade: Grade }) {
  const tone = gradeStyle[grade].tone
  const pos = `${Math.min(100, Math.max(0, score))}%`

  return (
    <div className="a2d-gauge" role="img" aria-label={`안전 점수 ${score}점, 100점 만점, ${grade} 등급`}>
      <div className="a2d-gauge-label" style={{ left: pos }}>{`현재 ${score}점`}</div>
      <div className="a2d-gauge-track">
        {BANDS.map((b) => (
          <div
            key={b.grade}
            className="a2d-gauge-band"
            style={{
              left: `${b.from}%`,
              width: `${b.to - b.from}%`,
              background: `var(--seed-color-bg-${gradeStyle[b.grade].tone}-weak)`,
            }}
          >
            {/* 점이 놓인 구간의 글자는 점에 가려지므로 비운다(등급은 옆 배지에 있다). */}
            {b.grade === grade ? null : b.grade}
          </div>
        ))}
        <div className="a2d-gauge-dot" style={{ left: pos, background: `var(--seed-color-fg-${tone})` }} />
      </div>
      <div className="a2d-gauge-ticks">
        {TICKS.map((t) => (
          <span key={t} style={{ left: `${t}%` }}>
            {t}
          </span>
        ))}
      </div>
    </div>
  )
}
