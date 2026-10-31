// 안전 점수 게이지. 0~100 가로 막대에 등급 구간 띠를 깔고, 현재 점수 자리에 점을 찍는다.
// 막대 그래프보다 "100점 중 어디쯤인지"가 바로 보이게 요약에서 쓴다.

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
const DOT = 18 // global.css .a2d-gauge-dot 지름

export function ScoreGauge({ score, grade }: { score: number; grade: Grade }) {
  const tone = gradeStyle[grade].tone
  const v = Math.min(100, Math.max(0, score))
  // 점은 막대 안쪽(양끝 반지름만큼 들임)에 찍고, 글자는 점수만큼 왼쪽으로 당겨
  // 0점이면 왼쪽 정렬, 100점이면 오른쪽 정렬이 되게 해 모달 밖으로 나가지 않게 한다.
  const dotLeft = `calc(${DOT / 2}px + (100% - ${DOT}px) * ${v / 100})`

  return (
    <div className="a2d-gauge" role="img" aria-label={`안전 점수 ${score}점, 100점 만점, ${grade} 등급`}>
      <div className="a2d-gauge-label" style={{ left: dotLeft, transform: `translateX(-${v}%)` }}>{`현재 ${score}점`}</div>
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
        <div className="a2d-gauge-dot" style={{ left: dotLeft, background: `var(--seed-color-fg-${tone})` }} />
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
