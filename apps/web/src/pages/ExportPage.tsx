// 4-5 한 장 요약 내보내기 (FR-13, P1). 별도 API 없이 summary와 history로 A4 한 장을 만들고,
// 브라우저 인쇄(PDF로 저장)로 내보낸다(API 명세 2장). 머리글과 메뉴는 없다.

import { Box, Grid, HStack, Text, VStack } from '@seed-design/react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ActionButton } from 'seed-design/ui/action-button'
import { getCurrentDomainId } from '../api/currentDomain'
import { api } from '../api/endpoints'
import logoUrl from '../assets/a2d-logo.svg'
import { GradeBadge, SeverityBadge } from '../components/Badges'
import { ScoreTrend } from '../components/ScoreTrend'
import { useApi } from '../hooks/useApi'
import { formatDateTime, formatMinutes } from '../lib/format'

export function ExportPage() {
  const domainId = getCurrentDomainId()
  if (!domainId) return <Navigate to="/register" replace />
  return <OnePager domainId={domainId} />
}

function OnePager({ domainId }: { domainId: string }) {
  const navigate = useNavigate()
  const summary = useApi(() => api.domains.summary(domainId), [domainId])
  const history = useApi(() => api.domains.history(domainId), [domainId])
  const s = summary.data

  return (
    <Box bg="bg.layerBasement" minHeight="100vh" py="x8" px="x4">
      {/* 인쇄할 때는 이 줄이 숨는다 */}
      <HStack className="a2d-no-print" justify="center" gap="x2" pb="x6">
        <ActionButton variant="neutralWeak" onClick={() => navigate(-1)}>
          돌아가기
        </ActionButton>
        <ActionButton variant="brandSolid" onClick={() => window.print()} disabled={!s}>
          인쇄 · PDF로 저장
        </ActionButton>
      </HStack>

      <Box className="a2d-page" bg="bg.layerDefault" mx="auto" p="x10" maxWidth="794px" borderRadius="r4" boxShadow="s2">
        {!s ? (
          <Text textStyle="t5Regular" color="fg.neutralMuted">
            불러오는 중…
          </Text>
        ) : (
          <VStack gap="x8">
            <HStack justify="space-between" align="center">
              <img src={logoUrl} alt="A2D" height={36} />
              <VStack align="flex-end" gap="x0_5">
                <Text textStyle="t5Bold" color="fg.neutral">
                  {s.domain}
                </Text>
                <Text textStyle="t3Regular" color="fg.neutralSubtle">
                  {s.latest_scan ? `${formatDateTime(s.latest_scan.finished_at)} 점검` : '점검 전'}
                </Text>
              </VStack>
            </HStack>

            <div className="a2d-flow-line" aria-hidden="true" />

            <HStack gap="x8" align="center" wrap>
              <VStack gap="x1">
                <Text textStyle="t3Bold" color="fg.neutralMuted">
                  안전 점수
                </Text>
                <HStack gap="x3" align="center">
                  <Text textStyle="t13Bold" color="fg.neutral">
                    {s.safety_score}
                  </Text>
                  <GradeBadge grade={s.grade} size="large" />
                </HStack>
              </VStack>
              <Text textStyle="t5Regular" color="fg.neutralMuted" style={{ flex: 1, minWidth: 240 }}>
                {s.today_tasks.length
                  ? `오늘 할 일 ${s.today_tasks.length}가지를 고치면 안전 점수가 ${s.today_tasks.at(-1)!.safety_score_after}점(${s.today_tasks.at(-1)!.grade_after})까지 오릅니다.`
                  : '지금 고칠 문제가 없습니다.'}
              </Text>
            </HStack>

            <VStack gap="x3">
              <Text textStyle="t5Bold" color="fg.neutral">
                오늘 할 일
              </Text>
              {s.today_tasks.map((t) => (
                <Grid key={t.finding_id} columns="28px 1fr auto" gap="x3" alignItems="center">
                  <Text textStyle="t6Bold" color="fg.brand">
                    {t.rank}
                  </Text>
                  <VStack gap="x0_5">
                    <HStack gap="x2" align="center">
                      <SeverityBadge severity={t.severity} />
                      <Text textStyle="t5Bold" color="fg.neutral">
                        {t.title}
                      </Text>
                    </HStack>
                    <Text textStyle="t3Regular" color="fg.neutralMuted">{`${t.asset_alias} · 조치 약 ${formatMinutes(t.fix_minutes)}`}</Text>
                  </VStack>
                  <Text textStyle="t4Bold" color="fg.positive">{`→ ${t.safety_score_after}점`}</Text>
                </Grid>
              ))}
            </VStack>

            {history.data && history.data.items.length > 0 && (
              <VStack gap="x3">
                <Text textStyle="t5Bold" color="fg.neutral">
                  안전 점수 추이
                </Text>
                <ScoreTrend items={history.data.items} selectedScanId={null} onSelect={() => undefined} />
              </VStack>
            )}

            <Text textStyle="t2Regular" color="fg.neutralSubtle">
              A2D는 소유권을 증명한 도메인만 읽기 전용으로 점검합니다. 점수 계산식과 근거는 A2D 화면의 기술 근거에서 볼 수 있습니다.
            </Text>
          </VStack>
        )}
      </Box>
    </Box>
  )
}
