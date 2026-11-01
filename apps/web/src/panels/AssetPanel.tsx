// 자산 상세 패널 (SEED SidePanel). 자산 정보와 자산 중요도 수정(1~5).
// 흐름: 중요도를 고르면 PATCH /domains/{id}/assets/{asset_id} → 서버가 점수를 다시 계산
//       → onChanged()로 대시보드가 요약을 다시 불러와 점수 카드가 새 값으로 움직인다.

import { HStack, Text, VStack } from '@seed-design/react'
import { useState } from 'react'
import { Badge } from 'seed-design/ui/badge'
import { Callout } from 'seed-design/ui/callout'
import { SegmentedControl, SegmentedControlItem } from 'seed-design/ui/segmented-control'
import { SidePanelBody, SidePanelContent, SidePanelRoot } from 'seed-design/ui/side-panel'
import { ApiError } from '../api/client'
import { api } from '../api/endpoints'
import type { Asset } from '../api/types'
import { SeverityBadge } from '../components/Badges'

interface AssetPanelProps {
  domainId: string
  asset: Asset | null
  onClose: () => void
  onChanged: () => void
}

const FOUND_BY: Record<number, string> = {
  1: '하위 도메인 찾기',
  2: '홈페이지 링크',
  3: 'robots.txt·사이트맵',
  4: '위탁 서비스 연결',
  5: '인증서 발급 기록',
}

export function AssetPanel({ domainId, asset, onClose, onChanged }: AssetPanelProps) {
  return (
    <SidePanelRoot open={asset !== null} onOpenChange={(open) => !open && onClose()}>
      <SidePanelContent title={asset?.alias ?? '자산'} description={asset?.host}>
        <SidePanelBody>
          {asset && <AssetDetail key={asset.asset_id} domainId={domainId} asset={asset} onChanged={onChanged} />}
        </SidePanelBody>
      </SidePanelContent>
    </SidePanelRoot>
  )
}

function AssetDetail({ domainId, asset, onChanged }: { domainId: string; asset: Asset; onChanged: () => void }) {
  const [importance, setImportance] = useState(String(asset.importance.value))
  const [message, setMessage] = useState<{ tone: 'positive' | 'critical'; text: string }>()

  const change = async (value: string) => {
    setImportance(value)
    try {
      const res = await api.domains.setAssetImportance(domainId, asset.asset_id, Number(value))
      setMessage({ tone: 'positive', text: `저장했습니다. 안전 점수가 ${res.summary.safety_score}점(${res.summary.grade})으로 다시 계산됐습니다.` })
      onChanged()
    } catch (e) {
      setImportance(String(asset.importance.value))
      setMessage({ tone: 'critical', text: e instanceof ApiError ? e.message : '저장하지 못했습니다.' })
    }
  }

  return (
    <VStack gap="x6" pb="x6">
      <HStack gap="x2" wrap>
        {asset.max_severity ? <SeverityBadge severity={asset.max_severity} size="large" /> : (
          <Badge tone="positive" variant="weak" size="large">
            이상 없음
          </Badge>
        )}
        <Badge tone="neutral" variant="weak" size="large">
          {`발견 ${asset.finding_count}건`}
        </Badge>
        {asset.tags.map((t) => (
          <Badge key={t} tone="neutral" variant="outline" size="large">
            {t}
          </Badge>
        ))}
      </HStack>

      <VStack gap="x3">
        <Text textStyle="t3Bold" color="fg.neutralMuted">
          자산 중요도
        </Text>
        <SegmentedControl aria-label="자산 중요도" value={importance} onValueChange={change}>
          {['1', '2', '3', '4', '5'].map((v) => (
            <SegmentedControlItem key={v} value={v}>
              {v}
            </SegmentedControlItem>
          ))}
        </SegmentedControl>
        <Text textStyle="t3Regular" color="fg.neutralSubtle">
          {asset.importance.source === 'auto'
            ? `자동 추정: ${asset.importance.rule ?? ''}. 틀렸다면 직접 고쳐 주세요. 점수가 다시 계산됩니다.`
            : '담당자가 직접 정한 값입니다.'}
        </Text>
        {message && <Callout tone={message.tone} description={message.text} />}
      </VStack>

      <VStack gap="x2">
        <Text textStyle="t3Bold" color="fg.neutralMuted">
          찾은 방법
        </Text>
        <HStack gap="x1_5" wrap>
          {asset.found_by.map((n) => (
            <Badge key={n} tone="neutral" variant="weak" size="medium">
              {`#${n} ${FOUND_BY[n] ?? ''}`}
            </Badge>
          ))}
        </HStack>
      </VStack>

      <VStack gap="x2">
        <Text textStyle="t3Bold" color="fg.neutralMuted">
          {`컴포넌트·버전 (#24)${asset.tls_version ? ` · ${asset.tls_version}` : ''}`}
        </Text>
        {asset.components.length === 0 ? (
          <Text textStyle="t4Regular" color="fg.neutralSubtle">
            식별된 컴포넌트가 없습니다.
          </Text>
        ) : (
          asset.components.map((c) => (
            <HStack key={c.name} justify="space-between" p="x3" borderRadius="r3" bg="bg.neutralWeak">
              <Text textStyle="t4Medium" color="fg.neutral">
                {`${c.name} ${c.version}`}
              </Text>
              {c.eol && (
                <Badge tone="warning" variant="weak" size="medium">
                  지원 종료
                </Badge>
              )}
            </HStack>
          ))
        )}
      </VStack>
    </VStack>
  )
}
