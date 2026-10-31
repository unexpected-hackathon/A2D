// 발견 등급·조직 등급·확실성 배지. 색과 글자는 theme/severity.ts에서만 가져온다.

import { Badge } from 'seed-design/ui/badge'
import type { Confidence, Grade, Severity } from '../api/types'
import { confidenceStyle, gradeStyle, severityStyle } from '../theme/severity'

export function SeverityBadge({ severity, size = 'medium' }: { severity: Severity; size?: 'medium' | 'large' }) {
  const s = severityStyle[severity]
  return (
    <Badge tone={s.tone} variant="solid" size={size}>
      {s.label}
    </Badge>
  )
}

export function GradeBadge({ grade, size = 'medium' }: { grade: Grade; size?: 'medium' | 'large' }) {
  const g = gradeStyle[grade]
  return (
    <Badge tone={g.tone} variant="weak" size={size}>
      {`${grade} · ${g.caption}`}
    </Badge>
  )
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const c = confidenceStyle[confidence]
  return (
    <Badge tone="neutral" variant={c.variant} size="medium">
      {c.label}
    </Badge>
  )
}
