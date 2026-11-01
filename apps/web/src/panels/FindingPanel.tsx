// 발견 상세 패널 (SEED SidePanel). 대시보드 발견 목록과 조치 가이드 "기술 근거 보기"가 같이 쓴다.
// 흐름: 부모가 findingId를 넘기면 열리고 → GET /findings/{id} → 점수 요소·계산식·마스킹된 증거를 보여 준다.
//       닫으면 부모의 onClose가 findingId를 비운다.

import { Grid, HStack, Skeleton, Text, VStack } from '@seed-design/react'
import { Callout } from 'seed-design/ui/callout'
import { SidePanelBody, SidePanelContent, SidePanelRoot } from 'seed-design/ui/side-panel'
import { api } from '../api/endpoints'
import { ConfidenceBadge, SeverityBadge } from '../components/Badges'
import { useApi } from '../hooks/useApi'
import { formatDateTime } from '../lib/format'

interface FindingPanelProps {
  findingId: string | null
  onClose: () => void
}

export function FindingPanel({ findingId, onClose }: FindingPanelProps) {
  return (
    <SidePanelRoot open={findingId !== null} onOpenChange={(open) => !open && onClose()}>
      <SidePanelContent title="기술 근거" description="이 발견을 어떻게 판정했고 점수가 어떻게 나왔는지 보여 줍니다.">
        <SidePanelBody>{findingId && <FindingDetailView findingId={findingId} />}</SidePanelBody>
      </SidePanelContent>
    </SidePanelRoot>
  )
}

const FACTORS = [
  { key: 'exposure', label: '노출도 E', hint: '누가 닿을 수 있나' },
  { key: 'exploitability', label: '악용 용이성 X', hint: '얼마나 쉽게' },
  { key: 'data_sensitivity', label: '데이터 민감도 D', hint: '무엇이 걸렸나' },
  { key: 'asset_importance', label: '자산 중요도 C', hint: '어떤 자산인가' },
] as const

function FindingDetailView({ findingId }: { findingId: string }) {
  const { data: f, error, loading } = useApi(() => api.findings.get(findingId), [findingId])

  if (error) return <Callout tone="critical" description={error.message} />
  if (loading || !f) {
    return (
      <VStack gap="x3" py="x2">
        <Skeleton radius="8" height="x6" width="60%" />
        <Skeleton radius="16" height="120px" width="full" />
        <Skeleton radius="16" height="80px" width="full" />
      </VStack>
    )
  }

  return (
    <VStack gap="x6" pb="x6">
      {/* 무엇이 발견됐나 */}
      <VStack gap="x2">
        <HStack gap="x2" align="center" wrap>
          <SeverityBadge severity={f.severity} size="large" />
          <ConfidenceBadge confidence={f.confidence} />
          <Text textStyle="t3Regular" color="fg.neutralSubtle">
            {`#${f.check_id} · ${f.finding_id}`}
          </Text>
        </HStack>
        <Text textStyle="t7Bold" color="fg.neutral">
          {f.check_name}
        </Text>
        <Text textStyle="t4Regular" color="fg.neutralMuted">
          {`${f.asset_alias} · ${f.situation}`}
        </Text>
      </VStack>

      <Section title="위치">
        <Code>{f.location}</Code>
      </Section>

      <Section title="점수 요소">
        <Grid columns={2} gap="x2">
          {FACTORS.map((factor) => (
            <VStack key={factor.key} gap="x0_5" p="x3" borderRadius="r3" bg="bg.neutralWeak">
              <Text textStyle="t2Medium" color="fg.neutralSubtle">
                {factor.label}
              </Text>
              <HStack gap="x1" align="flex-end">
                <Text textStyle="t7Bold" color="fg.neutral">
                  {f.score[factor.key]}
                </Text>
                <Text textStyle="t3Regular" color="fg.neutralSubtle">
                  / 5
                </Text>
              </HStack>
              <Text textStyle="t2Regular" color="fg.neutralSubtle">
                {factor.key === 'asset_importance' && f.score.asset_importance_fixed ? '조직 전체에 영향 · 고정값' : factor.hint}
              </Text>
            </VStack>
          ))}
        </Grid>
        <HStack justify="space-between" align="center" p="x3" borderRadius="r3" bg="bg.brandWeak">
          <Text textStyle="t4Medium" color="fg.brandContrast">
            {`신뢰도 계수 ${f.score.confidence_factor}`}
          </Text>
          <Text textStyle="t6Bold" color="fg.brandContrast">
            {`위험 점수 ${f.score.risk_score}`}
          </Text>
        </HStack>
        {f.score.formula && <Code>{f.score.formula}</Code>}
      </Section>

      <Section title="마스킹된 증거">
        <Code>{f.evidence}</Code>
        <Text textStyle="t2Regular" color="fg.neutralSubtle">
          개인정보와 비밀값은 가려서 저장합니다. 응답 원문은 보관하지 않습니다.
        </Text>
      </Section>

      {f.cves.length > 0 && (
        <Section title="알려진 취약점(CVE)">
          {f.cves.map((c) => (
            <Text key={c.id} textStyle="t4Regular" color="fg.neutral">
              {`${c.id} · CVSS ${c.cvss}${c.kev ? ' · 실제 악용 중' : ''}`}
            </Text>
          ))}
        </Section>
      )}

      <Text textStyle="t2Regular" color="fg.neutralSubtle">
        {`${formatDateTime(f.detected_at)} 발견 · 점검 ${f.scan_id}`}
      </Text>
    </VStack>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <VStack gap="x2">
      <Text textStyle="t3Bold" color="fg.neutralMuted">
        {title}
      </Text>
      {children}
    </VStack>
  )
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <Text
      as="p"
      textStyle="t3Regular"
      color="fg.neutral"
      style={{
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        background: 'var(--seed-color-bg-neutral-weak)',
        borderRadius: 10,
        padding: '10px 12px',
        overflowWrap: 'anywhere',
      }}
    >
      {children}
    </Text>
  )
}
