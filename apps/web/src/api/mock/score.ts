// 가짜 응답이 쓰는 점수 계산. docs/A2D_점검점수설계.md 2.1을 그대로 옮겼다.
// 실제 점수는 백엔드가 계산한다. 여기 있는 이유는 가짜 응답의 숫자가 명세와 맞게 하려는 것뿐이다.

import type { Confidence, Grade, Severity } from '../types'

const CONFIDENCE_FACTOR: Record<Confidence, number> = {
  confirmed: 1.0,
  likely: 0.8,
  needs_review: 0.6,
}

export interface Factors {
  e: number // 노출도
  x: number // 악용 용이성
  d: number // 데이터 민감도
  c: number // 자산 중요도
  confidence: Confidence
}

// 발견 위험 점수 (반올림 전 값)
export function riskRaw(f: Factors): number {
  const geo = (f.e * f.x * f.d * f.c) ** 0.25
  return ((100 * (geo - 1)) / 4) * CONFIDENCE_FACTOR[f.confidence]
}

export function riskFormula(f: Factors): string {
  return `100 × ((${f.e} × ${f.x} × ${f.d} × ${f.c})^(1/4) − 1) ÷ 4 × ${CONFIDENCE_FACTOR[f.confidence]} = ${Math.round(riskRaw(f))}`
}

export function confidenceFactor(c: Confidence): number {
  return CONFIDENCE_FACTOR[c]
}

// 조직 위험 점수 = 0.7 × 최고 + 0.3 × (다음 상위 5개 합 ÷ 5). 빈자리는 0.
export function orgRiskRaw(scores: number[]): number {
  const sorted = [...scores].sort((a, b) => b - a)
  const top = sorted[0] ?? 0
  const next = sorted.slice(1, 6).reduce((sum, s) => sum + s, 0)
  return 0.7 * top + 0.3 * (next / 5)
}

export function safetyScore(scores: number[]): number {
  return Math.round(100 - orgRiskRaw(scores))
}

export function gradeOf(safety: number): Grade {
  if (safety >= 90) return 'A'
  if (safety >= 72) return 'B'
  if (safety >= 58) return 'C'
  if (safety >= 44) return 'D'
  return 'F'
}

export function severityOf(risk: number): Severity {
  const r = Math.round(risk)
  if (r >= 80) return 'critical'
  if (r >= 60) return 'high'
  if (r >= 40) return 'medium'
  return 'low'
}

// 오늘 할 일: 고쳤을 때 안전 점수가 가장 많이 오르는 발견부터 3개 (FR-06).
// 같으면 위험 점수가 높은 것, 그다음 조치 시간이 짧은 것.
export function pickTodayTasks<T extends { id: string; risk: number; fixMinutes: number }>(
  findings: T[],
  count = 3,
): { finding: T; safetyAfter: number }[] {
  const remaining = [...findings]
  const picked: { finding: T; safetyAfter: number }[] = []
  while (picked.length < count && remaining.length > 0) {
    let best = 0
    let bestSafety = -1
    remaining.forEach((candidate, i) => {
      const after = 100 - orgRiskRaw(remaining.filter((_, j) => j !== i).map((f) => f.risk))
      const current = remaining[best]
      const better =
        after > bestSafety + 1e-9 ||
        (Math.abs(after - bestSafety) < 1e-9 &&
          (candidate.risk > current.risk ||
            (candidate.risk === current.risk && candidate.fixMinutes < current.fixMinutes)))
      if (better) {
        best = i
        bestSafety = after
      }
    })
    const [chosen] = remaining.splice(best, 1)
    picked.push({ finding: chosen, safetyAfter: Math.round(bestSafety) })
  }
  return picked
}
