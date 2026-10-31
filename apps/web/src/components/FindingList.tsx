// 2-6 발견 목록. 위쪽 칩으로 등급을 거르고, 누르면 발견 상세 패널이 열린다.
// 거르기는 이미 받은 목록에서 화면이 한다(발견 수가 적어 서버에 다시 묻지 않는다).

import { HStack, Text, VStack } from '@seed-design/react'
import { useState } from 'react'
import { ChipTabsCarousel, ChipTabsList, ChipTabsRoot, ChipTabsTrigger } from 'seed-design/ui/chip-tabs'
import { ResultSection } from 'seed-design/ui/result-section'
import type { FindingSummary, Severity } from '../api/types'
import { SEVERITY_ORDER, findingStatusLabel, severityStyle } from '../theme/severity'
import { ConfidenceBadge, SeverityBadge } from './Badges'
import { Surface } from './Surface'

const FILTERS: ('all' | Severity)[] = ['all', ...SEVERITY_ORDER]

interface FindingListProps {
  findings: FindingSummary[]
  onSelect: (findingId: string) => void
}

export function FindingList({ findings, onSelect }: FindingListProps) {
  const [filter, setFilter] = useState<string>('all')
  const shown = filter === 'all' ? findings : findings.filter((f) => f.severity === filter)

  return (
    <Surface p="x0">
      <VStack>
        <VStack gap="x3" px="x5" pt="x5" pb="x3">
          <HStack justify="space-between" align="flex-end">
            <Text textStyle="t5Bold" color="fg.neutral">
              발견
            </Text>
            <Text textStyle="t3Regular" color="fg.neutralSubtle">
              {`${findings.length}건`}
            </Text>
          </HStack>
          <ChipTabsRoot value={filter} onValueChange={setFilter} size="medium" variant="neutralOutline">
            <ChipTabsCarousel>
              <ChipTabsList>
              {FILTERS.map((f) => {
                const count = f === 'all' ? findings.length : findings.filter((x) => x.severity === f).length
                return (
                  <ChipTabsTrigger key={f} value={f}>
                    {`${f === 'all' ? '전체' : severityStyle[f].label} ${count}`}
                  </ChipTabsTrigger>
                )
              })}
              </ChipTabsList>
            </ChipTabsCarousel>
          </ChipTabsRoot>
        </VStack>

        {shown.length === 0 ? (
          <ResultSection size="medium" title="해당하는 발견이 없습니다" />
        ) : (
          shown.map((f) => (
            <button key={f.finding_id} type="button" onClick={() => onSelect(f.finding_id)} className="a2d-row">
              <HStack gap="x3" align="center" px="x5" py="x3">
                <SeverityBadge severity={f.severity} />
                <VStack gap="x0_5" grow className="a2d-min0">
                  <Text textStyle="t4Bold" color="fg.neutral">
                    {f.check_name}
                  </Text>
                  <Text textStyle="t3Regular" color="fg.neutralSubtle">
                    {`${f.asset_alias} · ${f.situation}`}
                  </Text>
                </VStack>
                {f.status === 'new' && (
                  <Text textStyle="t3Bold" color="fg.informative">
                    {findingStatusLabel.new}
                  </Text>
                )}
                <ConfidenceBadge confidence={f.confidence} />
                <Text textStyle="t5Bold" color="fg.neutral" className="a2d-keep" style={{ minWidth: 28, textAlign: 'right' }}>
                  {f.risk_score}
                </Text>
              </HStack>
            </button>
          ))
        )}
      </VStack>
    </Surface>
  )
}
