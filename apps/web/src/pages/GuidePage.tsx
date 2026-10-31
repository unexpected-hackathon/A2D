// 3. 조치 가이드 (정보 구조도 3장).
//
// 데이터 흐름
//   1) 주소에 scanId가 없으면 요약에서 최근 점검 ID를 찾아 /guide/:scanId로 바꾼다
//   2) GET /scans/{scanId}/report → 근거 검증 표시(3-1)와 카드 3장(3-2)
//   3) "기술 근거 보기" → FindingPanel(대시보드와 같은 패널)
//   4) 대시보드의 오늘 할 일에서 왔으면 주소 끝 #task-N 카드로 스크롤하고 잠깐 강조한다
//   5) 질문하기(3-3) → POST /scans/{scanId}/questions → 답과 근거 발견 링크

import { IconCheckmarkShieldFill, IconClockLine, IconExclamationmarkTriangleFill } from '@karrotmarket/react-monochrome-icon'
import { HStack, Icon, Skeleton, Text, VStack } from '@seed-design/react'
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ActionButton } from 'seed-design/ui/action-button'
import { Badge } from 'seed-design/ui/badge'
import { Callout } from 'seed-design/ui/callout'
import { ResultSection } from 'seed-design/ui/result-section'
import { TextField, TextFieldTextarea } from 'seed-design/ui/text-field'
import { ApiError } from '../api/client'
import { api } from '../api/endpoints'
import type { Answer, GuideItem } from '../api/types'
import { PageHeader } from '../components/PageHeader'
import { Surface } from '../components/Surface'
import { useApi } from '../hooks/useApi'
import { useDomain } from '../hooks/useDomain'
import { useScan } from '../hooks/useScan'
import { formatDateTime, formatMinutes } from '../lib/format'
import { FindingPanel } from '../panels/FindingPanel'

export function GuidePage() {
  const { scanId } = useParams()
  return scanId ? <Guide scanId={scanId} /> : <LatestGuideRedirect />
}

// 1) 주소에 점검 ID가 없으면 최근 점검으로 보낸다.
function LatestGuideRedirect() {
  const { domain } = useDomain()
  const { data, error } = useApi(() => api.domains.summary(domain.domain_id), [domain.domain_id])
  if (error) return <Callout tone="critical" description={error.message} />
  if (!data) return <Skeleton radius="16" height="320px" width="full" />
  if (!data.latest_scan) {
    return (
      <Surface>
        <ResultSection title="아직 조치 가이드가 없습니다" description="첫 점검이 끝나면 오늘 할 일과 조치 방법이 여기에 나타납니다." />
      </Surface>
    )
  }
  return <Navigate to={`/guide/${data.latest_scan.scan_id}`} replace />
}

function Guide({ scanId }: { scanId: string }) {
  const guide = useApi(() => api.scans.guide(scanId), [scanId])
  const [findingId, setFindingId] = useState<string | null>(null)
  const { hash } = useLocation()
  const focusRank = Number(hash.replace('#task-', '')) || null
  const allVerified =
    !!guide.data &&
    guide.data.verification.passed === guide.data.verification.total &&
    guide.data.items.every((i) => i.verified)

  // 4) #task-N 카드로 스크롤
  useEffect(() => {
    if (!guide.data || !focusRank) return
    document.getElementById(`task-${focusRank}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [guide.data, focusRank])

  return (
    <VStack gap="x8">
      <PageHeader
        eyebrow="조치 가이드"
        title="오늘 할 일, 이렇게 고치세요"
      />

      {guide.error && <Callout tone={guide.error.code === 'SCAN_NOT_FINISHED' ? 'informative' : 'critical'} description={guide.error.message} />}
      {!guide.data && !guide.error && (
        <VStack gap="x4">
          <Skeleton radius="16" height="64px" width="full" />
          <Skeleton radius="16" height="260px" width="full" />
          <Skeleton radius="16" height="260px" width="full" />
        </VStack>
      )}

      {guide.data && (
        <>
          {/* 3-1 근거 검증 표시 */}
          <Surface py="x4">
            <HStack gap="x3" align="center" wrap>
              <Icon
                svg={allVerified ? <IconCheckmarkShieldFill /> : <IconExclamationmarkTriangleFill />}
                color={allVerified ? 'fg.positive' : 'fg.warning'}
                size="x6"
              />
              <Text textStyle="t5Bold" color="fg.neutral">
                {`근거 검증 통과 ${guide.data.verification.passed}/${guide.data.verification.total}`}
              </Text>
              <Text textStyle="t4Regular" color="fg.neutralMuted">
                {allVerified
                  ? '모든 문장이 실제 발견과 연결돼 있습니다.'
                  : `${guide.data.verification.total - guide.data.verification.passed}개 항목은 근거 확인이 끝나지 않았습니다. 기술 근거를 함께 확인해 주세요.`}
              </Text>
              <HStack gap="x2" ml="auto" align="center" wrap>
                <Badge tone={guide.data.source === 'llm' ? 'brand' : 'neutral'} variant="weak" size="large">
                  {guide.data.source === 'llm' ? 'AI 설명' : '기본 가이드'}
                </Badge>
                <Text textStyle="t3Regular" color="fg.neutralSubtle">
                  {formatDateTime(guide.data.generated_at)}
                </Text>
              </HStack>
            </HStack>
          </Surface>

          {guide.data.source === 'template' && (
            <Callout tone="neutral" description="AI 모델이 응답하지 않아 미리 준비한 문장으로 안내합니다. 내용과 순서는 같습니다." />
          )}

          {guide.data.items.length === 0 ? (
            <Surface>
              <ResultSection title="오늘 고칠 것이 없습니다" description="새로 고칠 문제가 없습니다." />
            </Surface>
          ) : (
            <VStack gap="x4">
              {guide.data.items.map((item, i) => (
                <GuideCard
                  key={item.rank}
                  item={item}
                  index={i}
                  highlighted={item.rank === focusRank}
                  onShowEvidence={() => setFindingId(item.finding_ids[0])}
                />
              ))}
            </VStack>
          )}

          <RescanCallToAction />

          <QuestionBox scanId={scanId} onOpenFinding={setFindingId} />
        </>
      )}

      <FindingPanel findingId={findingId} onClose={() => setFindingId(null)} />
    </VStack>
  )
}

// 다 고쳤으면 재점검 (정보 구조도: 카드 아래 "고친 뒤 재점검"). 시작하면 대시보드로 가서 진행을 본다.
function RescanCallToAction() {
  const scan = useScan()
  const navigate = useNavigate()
  return (
    <Surface p="x6" bg="bg.brandWeak" borderColor="stroke.brandWeak">
      <HStack gap="x4" align="center" justify="space-between" wrap>
        <VStack gap="x1">
          <Text textStyle="t5Bold" color="fg.brandContrast">
            고쳤다면 바로 재점검하세요
          </Text>
          <Text textStyle="t4Regular" color="fg.neutralMuted">
            고친 항목은 "해결됨"으로 바뀌고 안전 점수가 다시 계산됩니다.
          </Text>
        </VStack>
        <ActionButton
          variant="brandSolid"
          loading={scan.isRunning}
          onClick={async () => {
            await scan.start()
            navigate('/dashboard')
          }}
        >
          고친 뒤 재점검
        </ActionButton>
      </HStack>
    </Surface>
  )
}

// 3-2 조치 카드 하나
function GuideCard({
  item,
  index,
  highlighted,
  onShowEvidence,
}: {
  item: GuideItem
  index: number
  highlighted: boolean
  onShowEvidence: () => void
}) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      id={`task-${item.rank}`}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.08 * index, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      style={{
        borderRadius: 18,
        boxShadow: highlighted ? '0 0 0 3px var(--seed-color-stroke-brand-solid)' : 'none',
        transition: 'box-shadow 0.4s ease',
        scrollMarginTop: 24,
      }}
    >
      <Surface p="x6">
        <VStack gap="x5">
          <HStack gap="x4" align="flex-start">
            <VStack
              align="center"
              justify="center"
              width="40px"
              height="40px"
              borderRadius="full"
              bg={index === 0 ? 'bg.brandSolid' : 'bg.brandWeak'}
              flexShrink={0}
            >
              <Text textStyle="t6Bold" color={index === 0 ? 'fg.onBrandSolid' : 'fg.brandContrast'}>
                {item.rank}
              </Text>
            </VStack>
            <VStack gap="x1" grow className="a2d-min0">
              <HStack gap="x2" align="center" wrap>
                <Text as="h2" textStyle="t7Bold" color="fg.neutral">
                  {item.title}
                </Text>
                {!item.verified && (
                  <Badge tone="warning" variant="weak" size="medium">
                    근거 확인 필요
                  </Badge>
                )}
              </HStack>
              <HStack gap="x3" align="center" wrap>
                <HStack gap="x1" align="center">
                  <Icon svg={<IconClockLine />} color="fg.neutralSubtle" size="x4" />
                  <Text textStyle="t3Regular" color="fg.neutralMuted">
                    {`조치 약 ${formatMinutes(item.fix_minutes)}`}
                  </Text>
                </HStack>
                <Text textStyle="t3Bold" color="fg.positive">
                  {`고치면 안전 점수 ${item.safety_score_after}점`}
                </Text>
              </HStack>
            </VStack>
          </HStack>

          <HStack gap="x4" align="stretch" wrap>
            <InfoBlock label="왜 위험한가" text={item.why_risky} />
            <InfoBlock label="예상 피해" text={item.expected_damage} tone="critical" />
          </HStack>

          <VStack gap="x2">
            <Text textStyle="t3Bold" color="fg.neutralMuted">
              조치 방법
            </Text>
            <VStack as="ol" gap="x2" style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
              {item.fix_steps.map((step, i) => (
                <HStack as="li" key={step} gap="x3" align="flex-start">
                  <Text textStyle="t4Bold" color="fg.brand" style={{ minWidth: 18 }}>
                    {i + 1}
                  </Text>
                  <Text textStyle="t5Regular" color="fg.neutral">
                    {step}
                  </Text>
                </HStack>
              ))}
            </VStack>
          </VStack>

          <HStack justify="space-between" align="center" gap="x2" wrap pt="x2" borderTopWidth={1} borderColor="stroke.neutralSubtle">
            <Text textStyle="t3Regular" color="fg.neutralSubtle">
              {`근거 발견 ${item.finding_ids.join(', ')}`}
            </Text>
            <ActionButton variant="neutralWeak" size="small" onClick={onShowEvidence}>
              기술 근거 보기
            </ActionButton>
          </HStack>
        </VStack>
      </Surface>
    </motion.div>
  )
}

function InfoBlock({ label, text, tone }: { label: string; text: string; tone?: 'critical' }) {
  return (
    <VStack gap="x1_5" p="x4" borderRadius="r3" bg={tone === 'critical' ? 'bg.criticalWeak' : 'bg.neutralWeak'} grow style={{ flexBasis: 260 }}>
      <Text textStyle="t3Bold" color={tone === 'critical' ? 'fg.critical' : 'fg.neutralMuted'}>
        {label}
      </Text>
      <Text textStyle="t5Regular" color="fg.neutral">
        {text}
      </Text>
    </VStack>
  )
}

// 3-3 질문하기 (P1). 답에는 근거 발견 링크가 붙고, 근거가 없으면 답하지 않는다.
function QuestionBox({ scanId, onOpenFinding }: { scanId: string; onOpenFinding: (id: string) => void }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const ask = async () => {
    if (!question.trim()) return
    setBusy(true)
    setError(undefined)
    try {
      setAnswer(await api.scans.ask(scanId, question))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '답을 받지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Surface p="x6">
      <VStack gap="x4">
        <VStack gap="x1">
          <Text textStyle="t5Bold" color="fg.neutral">
            궁금한 점 물어보기
          </Text>
          <Text textStyle="t4Regular" color="fg.neutralMuted">
            이번 점검 결과에 근거가 있는 질문에만 답합니다.
          </Text>
        </VStack>
        <TextField value={question} onValueChange={({ value }) => setQuestion(value)} maxGraphemeCount={500}>
          <TextFieldTextarea placeholder="예: 백업 파일은 왜 위험해요?" />
        </TextField>
        <HStack justify="flex-end">
          <ActionButton variant="brandSolid" loading={busy} disabled={!question.trim()} onClick={ask}>
            질문하기
          </ActionButton>
        </HStack>
        {error && <Callout tone="critical" description={error} />}
        {answer && (
          <Callout
            tone={answer.finding_ids.length ? 'informative' : 'neutral'}
            title={answer.finding_ids.length ? '답변' : '근거 없음'}
            description={answer.answer}
            linkProps={
              answer.finding_ids.length
                ? { children: `근거 ${answer.finding_ids[0]} 보기`, onClick: () => onOpenFinding(answer.finding_ids[0]) }
                : undefined
            }
          />
        )}
      </VStack>
    </Surface>
  )
}
