// 4. 기록 (정보 구조도 3장).
//
// 데이터 흐름
//   1) GET /domains/{id}/history → 점수 추이 그래프(4-1)와 점검 목록(4-2)
//   2) 점검을 고르면(기본: 가장 최근) GET /scans/{id}/changes(4-3), GET /scans/{id}/audit(4-4)
//   3) 재점검이 끝나면(useScan().finishedVersion) 1)을 다시 부르고 새 점검을 고른다
//   4) "요약 내보내기"(4-5) → 모달(ExportDialog)에서 인쇄

import { HStack, Skeleton, Text, VStack } from '@seed-design/react'
import { useState } from 'react'
import { Badge } from 'seed-design/ui/badge'
import { Callout } from 'seed-design/ui/callout'
import { ResultSection } from 'seed-design/ui/result-section'
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from 'seed-design/ui/tabs'
import { api } from '../api/endpoints'
import { AuditLog } from '../components/AuditLog'
import { ExportDialog } from '../components/ExportDialog'
import { GradeBadge } from '../components/Badges'
import { PageHeader } from '../components/PageHeader'
import { ScanChanges } from '../components/ScanChanges'
import { ScoreTrend } from '../components/ScoreTrend'
import { Surface } from '../components/Surface'
import { useApi } from '../hooks/useApi'
import { useDomain } from '../hooks/useDomain'
import { useCheckName } from '../hooks/useChecks'
import { useScan } from '../hooks/useScan'
import { formatDateTime } from '../lib/format'
import { FindingPanel } from '../panels/FindingPanel'

export function HistoryPage() {
  const { domain } = useDomain()
  return <History domainId={domain.domain_id} />
}

function History({ domainId }: { domainId: string }) {
  const scan = useScan()
  const history = useApi(() => api.domains.history(domainId), [domainId, scan.finishedVersion])
  const items = history.data?.items ?? []

  // 고른 점검이 없으면 가장 최근 점검을 보여 준다.
  const [picked, setPicked] = useState<string | null>(null)
  const selected = picked && items.some((i) => i.scan_id === picked) ? picked : (items.at(-1)?.scan_id ?? null)

  const [findingId, setFindingId] = useState<string | null>(null)
  const checkName = useCheckName()

  return (
    <VStack gap="x8">
      <PageHeader
        eyebrow="기록"
        title="점검할수록 안전해지는 기록"
        actions={<ExportDialog domainId={domainId} />}
      />

      {history.error && <Callout tone="critical" description={history.error.message} />}
      {!history.data && !history.error && <Skeleton radius="16" height="320px" width="full" />}

      {history.data && items.length === 0 && (
        <Surface>
          <ResultSection title="아직 기록이 없습니다" description="첫 점검이 끝나면 점수 추이가 여기에 쌓입니다." />
        </Surface>
      )}

      {items.length > 0 && (
        <>
          {/* 4-1 점수 추이 */}
          <Surface>
            <VStack gap="x3">
              <HStack justify="space-between" align="flex-end" gap="x2" wrap>
                <Text textStyle="t5Bold" color="fg.neutral">
                  안전 점수 추이
                </Text>
                <Text textStyle="t3Regular" color="fg.neutralSubtle">
                  {items.length === 1 ? '재점검하면 변화가 보입니다' : '점을 누르면 그 점검을 봅니다'}
                </Text>
              </HStack>
              <ScoreTrend items={items} selectedScanId={selected} onSelect={setPicked} />
            </VStack>
          </Surface>

          <div className="a2d-grid a2d-grid--side">
            {/* 4-2 점검 목록 (최근 것이 위) */}
            <Surface p="x0">
              <VStack>
                <Text textStyle="t5Bold" color="fg.neutral" style={{ padding: '20px 20px 12px' }}>
                  점검 목록
                </Text>
                {[...items].reverse().map((it) => (
                  <button
                    key={it.scan_id}
                    type="button"
                    className="a2d-row"
                    onClick={() => setPicked(it.scan_id)}
                    aria-current={it.scan_id === selected}
                    style={it.scan_id === selected ? { background: 'var(--seed-color-bg-brand-weak)' } : undefined}
                  >
                    <HStack gap="x3" align="center" px="x5" py="x3">
                      <VStack gap="x0_5" grow>
                        <Text textStyle="t4Bold" color="fg.neutral">
                          {it.scan_id}
                        </Text>
                        <Text textStyle="t3Regular" color="fg.neutralSubtle">
                          {formatDateTime(it.finished_at)}
                          {it.status === 'stopped' ? ' · 중지됨' : ''}
                        </Text>
                      </VStack>
                      <VStack align="flex-end" gap="x1">
                        <HStack gap="x1_5" align="center">
                          <Text textStyle="t5Bold" color="fg.neutral">
                            {it.safety_score}
                          </Text>
                          <GradeBadge grade={it.grade} />
                        </HStack>
                        <HStack gap="x1">
                          {it.resolved_count > 0 && (
                            <Badge tone="positive" variant="weak" size="medium">{`해결 ${it.resolved_count}`}</Badge>
                          )}
                          {it.new_count > 0 && <Badge tone="warning" variant="weak" size="medium">{`새 발견 ${it.new_count}`}</Badge>}
                        </HStack>
                      </VStack>
                    </HStack>
                  </button>
                ))}
              </VStack>
            </Surface>

            {/* 4-3 변화 · 4-4 감사 기록 */}
            {selected && (
              <Surface>
                <TabsRoot defaultValue="changes" triggerLayout="hug" size="medium">
                  <TabsList>
                    <TabsTrigger value="changes">변화</TabsTrigger>
                    <TabsTrigger value="audit">감사 기록</TabsTrigger>
                  </TabsList>
                  <TabsContent value="changes">
                    <VStack pt="x5">
                      <ChangesView scanId={selected} checkName={checkName} onOpenFinding={setFindingId} />
                    </VStack>
                  </TabsContent>
                  <TabsContent value="audit">
                    <VStack pt="x5">
                      <AuditView scanId={selected} />
                    </VStack>
                  </TabsContent>
                </TabsRoot>
              </Surface>
            )}
          </div>
        </>
      )}

      <FindingPanel findingId={findingId} onClose={() => setFindingId(null)} />
    </VStack>
  )
}

function ChangesView({
  scanId,
  checkName,
  onOpenFinding,
}: {
  scanId: string
  checkName: (id: number) => string
  onOpenFinding: (id: string) => void
}) {
  const { data, error } = useApi(() => api.scans.changes(scanId), [scanId])
  if (error) return <Callout tone="critical" description={error.message} />
  if (!data) return <Skeleton radius="16" height="160px" width="full" />
  return <ScanChanges changes={data} checkName={checkName} onOpenFinding={onOpenFinding} />
}

function AuditView({ scanId }: { scanId: string }) {
  const { data, error } = useApi(() => api.scans.audit(scanId), [scanId])
  if (error) return <Callout tone="critical" description={error.message} />
  if (!data) return <Skeleton radius="16" height="160px" width="full" />
  return <AuditLog entries={data.items} />
}
