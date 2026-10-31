// 2-5 자산 목록. 누르면 자산 상세 패널(중요도 수정)이 열린다.

import { HStack, Text, VStack } from '@seed-design/react'
import { Badge } from 'seed-design/ui/badge'
import type { Asset } from '../api/types'
import { SeverityBadge } from './Badges'
import { Surface } from './Surface'

interface AssetListProps {
  assets: Asset[]
  onSelect: (asset: Asset) => void
}

export function AssetList({ assets, onSelect }: AssetListProps) {
  // 문제가 있는 자산을 위로
  const sorted = [...assets].sort((a, b) => b.finding_count - a.finding_count)

  return (
    <Surface p="x0">
      <VStack>
        <HStack justify="space-between" align="flex-end" px="x5" pt="x5" pb="x3">
          <Text textStyle="t5Bold" color="fg.neutral">
            자산
          </Text>
          <Text textStyle="t3Regular" color="fg.neutralSubtle">
            {`인터넷에 열린 서버 ${assets.length}개`}
          </Text>
        </HStack>
        {sorted.map((asset) => (
          <button key={asset.asset_id} type="button" onClick={() => onSelect(asset)} className="a2d-row">
            <HStack gap="x3" align="center" px="x5" py="x3">
              <VStack gap="x0_5" grow className="a2d-min0">
                <HStack gap="x2" align="center">
                  <Text textStyle="t4Bold" color="fg.neutral">
                    {asset.alias}
                  </Text>
                  {asset.is_new && (
                    <Badge tone="informative" variant="solid" size="medium">
                      새 자산
                    </Badge>
                  )}
                </HStack>
                <Text textStyle="t3Regular" color="fg.neutralSubtle" maxLines={1}>
                  {asset.host}
                </Text>
              </VStack>
              <Badge tone="neutral" variant="outline" size="medium" className="a2d-keep">
                {`중요도 ${asset.importance.value}`}
              </Badge>
              {asset.max_severity ? (
                <SeverityBadge severity={asset.max_severity} />
              ) : (
                <Badge tone="positive" variant="weak" size="medium">
                  이상 없음
                </Badge>
              )}
            </HStack>
          </button>
        ))}
      </VStack>
    </Surface>
  )
}
