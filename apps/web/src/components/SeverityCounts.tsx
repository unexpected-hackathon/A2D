// 등급별 발견 수(긴급·높음·중간·낮음) 칸. 대시보드 점수 카드와 요약 모달이 함께 쓴다.

import { Text, VStack } from '@seed-design/react'
import type { Severity } from '../api/types'
import { SEVERITY_ORDER, severityStyle } from '../theme/severity'

export function SeverityCounts({ counts }: { counts: Record<Severity, number> }) {
  return (
    <div className="a2d-counts">
      {SEVERITY_ORDER.map((s) => (
        <VStack key={s} gap="x0_5" px="x3" py="x2" borderRadius="r3" bg="bg.neutralWeak">
          <Text textStyle="t2Medium" color="fg.neutralSubtle">
            {severityStyle[s].label}
          </Text>
          <Text textStyle="t6Bold" color={counts[s] ? 'fg.neutral' : 'fg.neutralSubtle'}>
            {counts[s]}
          </Text>
        </VStack>
      ))}
    </div>
  )
}
