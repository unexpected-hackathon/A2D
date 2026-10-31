// 2. 대시보드 (정보 구조도 3장).
//
// 데이터 흐름
//   1) 도메인 ID → GET /domains/{id}/summary  (점수, 오늘 할 일, 최근 점검 ID)
//   2) 최근 점검 ID → GET /scans/{id}/assets, GET /scans/{id}/findings
//   3) 행을 누르면 패널 상태(selectedAsset / selectedFindingId)에 값을 넣어 패널을 연다
//   4) 자산 중요도를 고치면 1)·2)를 다시 불러와 점수가 바뀐다
//   5) 재점검: 점수 카드 버튼 → useScan().start() → 점검이 끝나 finishedVersion이 오르면 1)·2)를 다시 부른다
//   6) 새 노출 알림(2-4): summary.alerts

import { IconBellFill } from '@karrotmarket/react-monochrome-icon'
import { Grid, Skeleton, VStack } from '@seed-design/react'
import { useState } from 'react'
import { Callout } from 'seed-design/ui/callout'
import { ActionablePageBanner } from 'seed-design/ui/page-banner'
import { ResultSection } from 'seed-design/ui/result-section'
import { api } from '../api/endpoints'
import type { Asset } from '../api/types'
import { AssetList } from '../components/AssetList'
import { FindingList } from '../components/FindingList'
import { PageHeader } from '../components/PageHeader'
import { ScoreCard } from '../components/ScoreCard'
import { Surface } from '../components/Surface'
import { TodayTasks } from '../components/TodayTasks'
import { useApi } from '../hooks/useApi'
import { useDomain } from '../hooks/useDomain'
import { useScan } from '../hooks/useScan'
import { AssetPanel } from '../panels/AssetPanel'
import { FindingPanel } from '../panels/FindingPanel'

export function DashboardPage() {
  // 도메인이 없으면 AppShell(DomainProvider)이 등록 화면으로 먼저 보낸다.
  const { domain } = useDomain()
  return <Dashboard domainId={domain.domain_id} />
}

function Dashboard({ domainId }: { domainId: string }) {
  const scan = useScan()
  // 점검이 끝날 때마다(finishedVersion) 요약을 다시 불러온다.
  const summary = useApi(() => api.domains.summary(domainId), [domainId, scan.finishedVersion])
  const scanId = summary.data?.latest_scan?.scan_id

  // 최근 점검이 정해진 뒤에 자산·발견을 부른다.
  const assets = useApi(() => (scanId ? api.scans.assets(scanId) : Promise.resolve({ items: [] })), [scanId])
  const findings = useApi(() => (scanId ? api.scans.findings(scanId) : Promise.resolve({ items: [] })), [scanId])
  const assetList = assets.data?.items ?? []

  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null)
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null)

  const reloadAll = () => {
    void summary.reload()
    void assets.reload()
    void findings.reload()
  }

  return (
    <VStack gap="x8">
      <PageHeader
        eyebrow={summary.data?.domain ?? '대시보드'}
        title="오늘의 외부 노출 상태"
        description="안전 점수와 오늘 가장 먼저 고칠 3가지를 한눈에 봅니다."
      />

      {summary.error && (
        <Callout
          tone="critical"
          title="불러오지 못했습니다"
          description={summary.error.message}
          linkProps={{ children: '다시 시도', onClick: () => void summary.reload() }}
        />
      )}

      {!summary.data && !summary.error && <DashboardSkeleton />}

      {summary.data && !summary.data.latest_scan && (
        <Surface>
          <ResultSection
            title="아직 끝난 점검이 없습니다"
            description="첫 점검이 끝나면 안전 점수와 오늘 할 일이 여기에 나타납니다."
          />
        </Surface>
      )}

      {/* 2-4 새 노출 알림: 직전 점검에 없던 자산·발견. 누르면 해당 패널을 연다 */}
      {summary.data?.alerts.map((alert) => (
        <ActionablePageBanner
          key={`${alert.type}-${alert.asset_id}-${alert.finding_id}`}
          tone="warning"
          variant="weak"
          prefixIcon={<IconBellFill />}
          title={alert.type === 'new_asset' ? '새 노출 자산' : '새 발견'}
          description={alert.message}
          onClick={() => {
            if (alert.finding_id) setSelectedFindingId(alert.finding_id)
            else setSelectedAsset(assetList.find((a) => a.asset_id === alert.asset_id) ?? null)
          }}
          style={{ borderRadius: 16 }}
        />
      ))}

      {summary.data?.latest_scan && (
        <>
          {/* 넓은 화면에서 점수 카드 : 오늘 할 일 = 2 : 3 */}
          <Grid columns={{ base: 1, lg: '2fr 3fr' }} gap="x5">
            <ScoreCard summary={summary.data} onRescan={() => void scan.start()} scanning={scan.isRunning} />
            <TodayTasks
              scanId={summary.data.latest_scan.scan_id}
              tasks={summary.data.today_tasks}
              currentScore={summary.data.safety_score}
            />
          </Grid>
          <Grid columns={{ base: 1, lg: 2 }} gap="x5" alignItems="flex-start">
            {assets.data ? <AssetList assets={assets.data.items} onSelect={setSelectedAsset} /> : <ListSkeleton />}
            {findings.data ? (
              <FindingList findings={findings.data.items} onSelect={setSelectedFindingId} />
            ) : (
              <ListSkeleton />
            )}
          </Grid>
        </>
      )}

      <AssetPanel
        domainId={domainId}
        asset={selectedAsset}
        onClose={() => setSelectedAsset(null)}
        onChanged={reloadAll}
      />
      <FindingPanel findingId={selectedFindingId} onClose={() => setSelectedFindingId(null)} />
    </VStack>
  )
}

function DashboardSkeleton() {
  return (
    <Grid columns={{ base: 1, lg: '2fr 3fr' }} gap="x5">
      <Skeleton radius="16" height="300px" width="full" />
      <Skeleton radius="16" height="300px" width="full" />
    </Grid>
  )
}

function ListSkeleton() {
  return <Skeleton radius="16" height="260px" width="full" />
}
