// 4-4 감사 기록 (FR-16): 모든 도구 호출의 시각·주체·도구·인자·결과·거부 사유.
// 위쪽 칩으로 주체를 거르고, "거부만"으로 가드가 막은 호출만 볼 수 있다.

import { Box, HStack, Text, VStack } from '@seed-design/react'
import { useState } from 'react'
import { Badge } from 'seed-design/ui/badge'
import { ChipTabsList, ChipTabsRoot, ChipTabsTrigger } from 'seed-design/ui/chip-tabs'
import { ResultSection } from 'seed-design/ui/result-section'
import type { AuditEntry } from '../api/types'

const ACTOR: Record<AuditEntry['actor'], { label: string; tone: 'neutral' | 'warning' | 'brand' }> = {
  system: { label: '코드', tone: 'neutral' },
  attack: { label: 'Attack', tone: 'warning' },
  defense: { label: 'Defense', tone: 'brand' },
}
const FILTERS = [
  { value: 'all', label: '전체' },
  { value: 'system', label: '코드' },
  { value: 'attack', label: 'Attack' },
  { value: 'defense', label: 'Defense' },
  { value: 'rejected', label: '거부만' },
]

const time = (iso: string) =>
  new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Seoul' }).format(new Date(iso))

export function AuditLog({ entries }: { entries: AuditEntry[] }) {
  const [filter, setFilter] = useState('all')
  const shown = entries.filter((e) => (filter === 'all' ? true : filter === 'rejected' ? e.rejected : e.actor === filter))

  return (
    <VStack gap="x4">
      <ChipTabsRoot value={filter} onValueChange={setFilter} size="medium" variant="neutralOutline">
        <ChipTabsList>
          {FILTERS.map((f) => (
            <ChipTabsTrigger key={f.value} value={f.value}>
              {f.label}
            </ChipTabsTrigger>
          ))}
        </ChipTabsList>
      </ChipTabsRoot>

      {shown.length === 0 ? (
        <ResultSection size="medium" title="해당하는 기록이 없습니다" />
      ) : (
        <VStack gap="x2">
          {shown.map((e, i) => (
            <Box
              key={`${e.at}-${i}`}
              p="x3"
              borderRadius="r3"
              borderWidth={1}
              borderColor={e.rejected ? 'stroke.criticalWeak' : 'stroke.neutralSubtle'}
              bg={e.rejected ? 'bg.criticalWeak' : 'bg.layerDefault'}
            >
              <HStack gap="x3" align="flex-start" wrap>
                <Text textStyle="t3Regular" color="fg.neutralSubtle" style={{ fontVariantNumeric: 'tabular-nums', minWidth: 64 }}>
                  {time(e.at)}
                </Text>
                <Badge tone={ACTOR[e.actor].tone} variant="weak" size="medium">
                  {ACTOR[e.actor].label}
                </Badge>
                <VStack gap="x0_5" grow style={{ minWidth: 0 }}>
                  <Text textStyle="t4Bold" color="fg.neutral" style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                    {e.tool}
                  </Text>
                  <Text textStyle="t3Regular" color="fg.neutralMuted" style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', overflowWrap: 'anywhere' }}>
                    {JSON.stringify(e.args)}
                  </Text>
                </VStack>
                <Text textStyle="t4Medium" color={e.rejected ? 'fg.critical' : 'fg.neutral'}>
                  {e.rejected ? `거부: ${e.reject_reason}` : (e.result_summary ?? '')}
                </Text>
              </HStack>
            </Box>
          ))}
        </VStack>
      )}
    </VStack>
  )
}
