// 2-1 안전 점수·등급 카드.
// 원형 게이지가 점수만큼 차오르고, 가운데 숫자는 SEED AnimateNumber로 굴러가며 바뀐다.
// 재점검으로 점수가 바뀌면 같은 모션으로 새 값까지 움직인다.

import { HStack, Text, VStack } from '@seed-design/react'
import { motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'
import AnimateNumber from 'seed-design/breeze/animate-number/animate-number'
import { ActionButton } from 'seed-design/ui/action-button'
import type { Summary } from '../api/types'
import { formatDateTime } from '../lib/format'
import { gradeStyle } from '../theme/severity'
import { GradeBadge } from './Badges'
import { SeverityCounts } from './SeverityCounts'
import { Surface } from './Surface'

// SEED 상태 색(tone) → 게이지 선 색
const TONE_COLOR: Record<string, string> = {
  critical: 'var(--seed-color-fg-critical)',
  warning: 'var(--seed-color-fg-warning)',
  informative: 'var(--seed-color-fg-informative)',
  positive: 'var(--seed-color-fg-positive)',
}

const SIZE = 168
const STROKE = 14
const R = (SIZE - STROKE) / 2

interface ScoreCardProps {
  summary: Summary
  onRescan: () => void // 5단계: 재점검 (useScan().start)
  scanning: boolean
}

export function ScoreCard({ summary, onRescan, scanning }: ScoreCardProps) {
  const reduce = useReducedMotion()
  const [showFormula, setShowFormula] = useState(false)
  const tone = gradeStyle[summary.grade].tone
  const color = TONE_COLOR[tone] ?? 'var(--seed-color-fg-brand)'

  return (
    <Surface display="flex" flexDirection="column">
      <VStack gap="x5" grow>
        <HStack justify="space-between" align="center" gap="x2" wrap>
          <HStack gap="x2" align="center" wrap>
            <Text textStyle="t5Bold" color="fg.neutral">
              안전 점수
            </Text>
            <GradeBadge grade={summary.grade} size="large" />
          </HStack>
          <ActionButton variant="brandSolid" size="small" loading={scanning} onClick={onRescan}>
            {scanning ? '점검 중' : '재점검'}
          </ActionButton>
        </HStack>

        <div className="a2d-score-body">
          {/* 원형 게이지: 회색 바탕 원 위에 점수 비율만큼 색 원을 그린다 */}
          <div style={{ position: 'relative', width: SIZE, height: SIZE, flexShrink: 0 }}>
            <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} style={{ transform: 'rotate(-90deg)' }} aria-hidden="true">
              <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="var(--seed-color-bg-neutral-weak)" strokeWidth={STROKE} />
              <motion.circle
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={R}
                fill="none"
                stroke={color}
                strokeWidth={STROKE}
                strokeLinecap="round"
                initial={reduce ? false : { pathLength: 0 }}
                animate={{ pathLength: summary.safety_score / 100 }}
                transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
              />
            </svg>
            <VStack
              align="center"
              justify="center"
              gap="x0_5"
              style={{ position: 'absolute', inset: 0 }}
              aria-label={`안전 점수 ${summary.safety_score}점, ${summary.grade} 등급`}
            >
              <AnimateNumber value={summary.safety_score} fontSize={52} fontWeight={800} color={color} />
              <Text textStyle="t3Medium" color="fg.neutralSubtle">
                / 100
              </Text>
            </VStack>
          </div>

          <VStack gap="x3" className="a2d-score-text">
            {/* 등급별 발견 수 */}
            <SeverityCounts counts={summary.counts} />
          </VStack>
        </div>

        <VStack gap="x2" mt="auto">
          <HStack justify="space-between" align="center" gap="x2" wrap>
            <Text textStyle="t3Regular" color="fg.neutralSubtle">
              {summary.latest_scan ? `${formatDateTime(summary.latest_scan.finished_at)} 점검` : '아직 점검 전'}
            </Text>
            {summary.score_formula && (
              <ActionButton variant="ghost" size="xsmall" onClick={() => setShowFormula((v) => !v)}>
                {showFormula ? '산식 접기' : '산식 보기'}
              </ActionButton>
            )}
          </HStack>
          {showFormula && (
            <Text
              as="p"
              textStyle="t3Regular"
              color="fg.neutralMuted"
              style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}
            >
              {`조직 위험 ${summary.score_formula} → 안전 점수 100 − ${summary.org_risk_score} = ${summary.safety_score}`}
            </Text>
          )}
        </VStack>
      </VStack>
    </Surface>
  )
}
