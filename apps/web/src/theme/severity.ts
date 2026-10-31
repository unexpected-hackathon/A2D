// 등급·상태 코드 → 화면 글자와 SEED 색(tone)을 한 곳에서만 정한다.
// 화면은 색을 직접 고르지 않고 이 표만 쓴다. 색과 함께 항상 글자를 보인다(PRD 5장).

import type { Confidence, FindingStatus, Grade, Severity } from '../api/types'

type Tone = 'neutral' | 'brand' | 'informative' | 'positive' | 'warning' | 'critical'

export const severityStyle: Record<Severity, { label: string; tone: Tone }> = {
  critical: { label: '긴급', tone: 'critical' },
  high: { label: '높음', tone: 'warning' },
  medium: { label: '중간', tone: 'informative' },
  low: { label: '낮음', tone: 'neutral' },
  info: { label: '참고 정보', tone: 'neutral' },
}

export const gradeStyle: Record<Grade, { tone: Tone; caption: string }> = {
  A: { tone: 'positive', caption: '안전' },
  B: { tone: 'positive', caption: '양호' },
  C: { tone: 'informative', caption: '보통' },
  D: { tone: 'warning', caption: '주의' },
  F: { tone: 'critical', caption: '위험' },
}

// 안전 점수의 등급 구간(A 90+ / B 72+ / C 58+ / D 44+ / F). 점수 추이 그래프와 게이지가 함께 쓴다.
// 띠 색은 gradeStyle의 tone에서 가져온다: var(--seed-color-bg-{tone}-weak)
export const GRADE_BANDS: { grade: Grade; from: number; to: number }[] = [
  { grade: 'F', from: 0, to: 44 },
  { grade: 'D', from: 44, to: 58 },
  { grade: 'C', from: 58, to: 72 },
  { grade: 'B', from: 72, to: 90 },
  { grade: 'A', from: 90, to: 100 },
]

// 발견 등급을 보여 주는 순서(참고 정보는 개수에 넣지 않는다).
export const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low']

// 확실성은 같은 색에서 표시 방식만 바꾼다: 진하게 → 옅게 → 테두리만.
export const confidenceStyle: Record<
  Confidence,
  { label: string; variant: 'solid' | 'weak' | 'outline' }
> = {
  confirmed: { label: '확인됨', variant: 'solid' },
  likely: { label: '가능성', variant: 'weak' },
  needs_review: { label: '확인 필요', variant: 'outline' },
}

export const findingStatusLabel: Record<FindingStatus, string> = {
  open: '열림',
  new: '새 발견',
  resolved: '해결됨',
}
