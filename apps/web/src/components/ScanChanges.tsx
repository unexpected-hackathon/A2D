// 4-3 점검별 변화: 직전 점검과 비교한 점수 전후, 해결됨·새 발견·새 자산.

import { HStack, Text, VStack } from '@seed-design/react'
import { Badge } from 'seed-design/ui/badge'
import { ResultSection } from 'seed-design/ui/result-section'
import type { ChangedFinding, Changes } from '../api/types'
import { GradeBadge } from './Badges'

interface ScanChangesProps {
  changes: Changes
  checkName: (id: number) => string
  onOpenFinding: (findingId: string) => void
}

export function ScanChanges({ changes, checkName, onOpenFinding }: ScanChangesProps) {
  const { safety_score: score, grade } = changes
  const diff = score.before === null ? null : score.after - score.before

  return (
    <VStack gap="x5">
      {/* 점수 전후 */}
      <HStack gap="x4" align="center" wrap p="x4" borderRadius="r3" bg="bg.neutralWeak">
        {score.before !== null && grade.before ? (
          <>
            <VStack gap="x1">
              <Text textStyle="t2Medium" color="fg.neutralSubtle">
                직전
              </Text>
              <HStack gap="x2" align="center">
                <Text textStyle="t8Bold" color="fg.neutralMuted">
                  {score.before}
                </Text>
                <GradeBadge grade={grade.before} />
              </HStack>
            </VStack>
            <Text textStyle="t7Bold" color="fg.neutralSubtle">
              →
            </Text>
          </>
        ) : (
          <Text textStyle="t4Regular" color="fg.neutralMuted">
            첫 점검이라 비교할 직전 점검이 없습니다.
          </Text>
        )}
        <VStack gap="x1">
          <Text textStyle="t2Medium" color="fg.neutralSubtle">
            이번
          </Text>
          <HStack gap="x2" align="center">
            <Text textStyle="t8Bold" color="fg.neutral">
              {score.after}
            </Text>
            <GradeBadge grade={grade.after} />
          </HStack>
        </VStack>
        {diff !== null && diff !== 0 && (
          <Badge tone={diff > 0 ? 'positive' : 'critical'} variant="solid" size="large">
            {diff > 0 ? `+${diff}점` : `${diff}점`}
          </Badge>
        )}
      </HStack>

      <ChangeGroup title="해결됨" tone="positive" items={changes.resolved_findings} checkName={checkName} onOpen={onOpenFinding} />
      <ChangeGroup title="새 발견" tone="warning" items={changes.new_findings} checkName={checkName} onOpen={onOpenFinding} />

      {changes.new_assets.length > 0 && (
        <VStack gap="x2">
          <Text textStyle="t3Bold" color="fg.neutralMuted">
            새 자산
          </Text>
          {changes.new_assets.map((a) => (
            <HStack key={a.asset_id} gap="x2" align="center">
              <Badge tone="informative" variant="solid" size="medium">
                새 자산
              </Badge>
              <Text textStyle="t4Medium" color="fg.neutral">{`${a.alias} · ${a.host}`}</Text>
            </HStack>
          ))}
        </VStack>
      )}

      {changes.resolved_findings.length === 0 && changes.new_findings.length === 0 && changes.new_assets.length === 0 && (
        <ResultSection size="medium" title="바뀐 것이 없습니다" description="직전 점검과 발견이 같습니다." />
      )}
    </VStack>
  )
}

function ChangeGroup({
  title,
  tone,
  items,
  checkName,
  onOpen,
}: {
  title: string
  tone: 'positive' | 'warning'
  items: ChangedFinding[]
  checkName: (id: number) => string
  onOpen: (findingId: string) => void
}) {
  if (items.length === 0) return null
  return (
    <VStack gap="x2">
      <Text textStyle="t3Bold" color="fg.neutralMuted">
        {`${title} ${items.length}건`}
      </Text>
      {items.map((f) => (
        <button key={f.finding_id} type="button" className="a2d-row" onClick={() => onOpen(f.finding_id)} style={{ borderRadius: 10 }}>
          <HStack gap="x3" align="center" px="x3" py="x2_5">
            <Badge tone={tone} variant="weak" size="medium">
              {title}
            </Badge>
            <Text textStyle="t4Medium" color="fg.neutral">
              {checkName(f.check_id)}
            </Text>
            <Text textStyle="t3Regular" color="fg.neutralSubtle">
              {`${f.asset_alias} · ${f.finding_id}`}
            </Text>
            <Text textStyle="t4Bold" color="fg.neutralMuted" style={{ marginLeft: 'auto' }}>
              {f.risk_score}
            </Text>
          </HStack>
        </button>
      ))}
    </VStack>
  )
}
