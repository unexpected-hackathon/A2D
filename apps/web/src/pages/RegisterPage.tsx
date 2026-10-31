// 1. 등록 (정보 구조도 3장, FR-01). 한 화면에서 세 단계를 차례로 진행한다.
//
//   1-1 도메인 입력  → POST /domains (TXT 값 발급)
//   1-2 소유권 확인  → DNS에 TXT를 넣고 "확인" → POST /domains/{id}/verify
//                     실패하면 이 단계에 머물며 서버가 준 이유를 보여 준다
//   1-3 범위·안전 원칙 → "점검 시작" → POST /domains/{id}/scans → 대시보드(진행 띠가 이어 받는다)

import { IconCheckmarkCircleFill } from '@karrotmarket/react-monochrome-icon'
import { HStack, Icon, Text, VStack } from '@seed-design/react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ActionButton } from 'seed-design/ui/action-button'
import { Badge } from 'seed-design/ui/badge'
import { Callout } from 'seed-design/ui/callout'
import { TextField, TextFieldInput } from 'seed-design/ui/text-field'
import { ApiError } from '../api/client'
import { setStoredDomainId } from '../api/currentDomain'
import { api } from '../api/endpoints'
import type { Domain } from '../api/types'
import { Surface } from '../components/Surface'
import { useApi } from '../hooks/useApi'
import { AuthLayout } from '../layout/AuthLayout'

type Step = 'input' | 'verify' | 'ready'
const STEPS: { key: Step; label: string }[] = [
  { key: 'input', label: '도메인 입력' },
  { key: 'verify', label: '소유권 확인' },
  { key: 'ready', label: '점검 시작' },
]

const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

export function RegisterPage() {
  const [step, setStep] = useState<Step>('input')
  const [domain, setDomain] = useState<Domain>()
  const navigate = useNavigate()
  // 이미 도메인이 있는 사용자가 "도메인 추가"로 들어왔으면 돌아갈 수 있게 한다.
  const existing = useApi(() => api.domains.list(), [])
  const hasDomains = (existing.data?.items.length ?? 0) > 0

  const stepIndex = STEPS.findIndex((s) => s.key === step)

  return (
    <AuthLayout>
      <VStack gap="x6">
        <VStack gap="x3">
          {/* 단계 표시 */}
          <HStack gap="x1_5" wrap>
            {STEPS.map((s, i) => (
              <Badge key={s.key} tone={i <= stepIndex ? 'brand' : 'neutral'} variant={i === stepIndex ? 'solid' : 'weak'} size="medium">
                {`${i + 1} ${s.label}`}
              </Badge>
            ))}
          </HStack>
          <HStack justify="space-between" align="center">
            <Text as="h1" textStyle="t9Bold" color="fg.neutral">
              점검할 도메인 등록
            </Text>
            {hasDomains && step !== 'ready' && (
              <ActionButton variant="ghost" size="small" onClick={() => navigate('/dashboard')}>
                돌아가기
              </ActionButton>
            )}
          </HStack>
        </VStack>

        <Surface p="x6">
          {step === 'input' && (
            <DomainInput
              onCreated={(d) => {
                setDomain(d)
                setStep(d.verify_status === 'verified' ? 'ready' : 'verify')
              }}
            />
          )}
          {step === 'verify' && domain && <VerifyOwnership domain={domain} onVerified={() => setStep('ready')} />}
          {step === 'ready' && domain && <StartScan domain={domain} />}
        </Surface>
      </VStack>
    </AuthLayout>
  )
}

// 1-1
function DomainInput({ onCreated }: { onCreated: (d: Domain) => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(undefined)
    try {
      onCreated(await api.domains.create(value.trim()))
    } catch (err) {
      setError(errorText(err, '도메인을 등록하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <VStack gap="x5">
        <TextField
          label="회사 도메인"
          description="소유권을 증명한 도메인과 그 하위 자산만 점검합니다."
          value={value}
          onValueChange={({ value: v }) => setValue(v)}
          errorMessage={error}
          invalid={!!error}
        >
          <TextFieldInput placeholder="jobnest.test" autoComplete="off" />
        </TextField>
        <ActionButton type="submit" variant="brandSolid" size="large" loading={busy} disabled={!value.trim()}>
          다음
        </ActionButton>
      </VStack>
    </form>
  )
}

// 1-2
function VerifyOwnership({ domain, onVerified }: { domain: Domain; onVerified: () => void }) {
  const [reason, setReason] = useState<string>()
  const [busy, setBusy] = useState(false)

  const verify = async () => {
    setBusy(true)
    setReason(undefined)
    try {
      const res = await api.domains.verify(domain.domain_id)
      if (res.verify_status === 'verified') onVerified()
      else setReason(res.reason ?? 'TXT 레코드를 찾지 못했습니다.')
    } catch (err) {
      setReason(errorText(err, '확인하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <VStack gap="x5">
      <Text textStyle="t4Regular" color="fg.neutralMuted">
        {`${domain.domain}의 DNS에 아래 TXT 레코드를 넣은 뒤 "확인"을 누르세요. DNS 반영에 몇 분이 걸릴 수 있습니다.`}
      </Text>
      <CopyRow label="이름" value={domain.txt_record.name} />
      <CopyRow label="값" value={domain.txt_record.value} />
      {reason && <Callout tone="critical" title="아직 확인되지 않았습니다" description={reason} />}
      <ActionButton variant="brandSolid" size="large" loading={busy} onClick={verify}>
        확인
      </ActionButton>
    </VStack>
  )
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // 복사가 막힌 환경에서는 글자를 직접 선택하면 된다.
    }
  }
  return (
    <HStack gap="x3" align="center" p="x3" borderRadius="r3" bg="bg.neutralWeak">
      <Text textStyle="t3Bold" color="fg.neutralMuted" style={{ minWidth: 32 }}>
        {label}
      </Text>
      <Text textStyle="t4Regular" color="fg.neutral" style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', overflowWrap: 'anywhere', flex: 1 }}>
        {value}
      </Text>
      <ActionButton variant="neutralWeak" size="xsmall" onClick={copy}>
        {copied ? '복사됨' : '복사'}
      </ActionButton>
    </HStack>
  )
}

// 1-3
const PRINCIPLES = [
  '소유권을 증명한 도메인과 그 하위 자산만 점검합니다.',
  '읽기 요청(GET·HEAD)만 보냅니다. 로그인 시도나 쓰기는 하지 않습니다.',
  '호스트당 초당 2건까지만 요청하고, 같은 페이지는 다시 열지 않습니다. 언제든 중지할 수 있습니다.',
  '개인정보와 비밀값은 가려서 저장하고, 응답 원문은 보관하지 않습니다.',
]

function StartScan({ domain }: { domain: Domain }) {
  const navigate = useNavigate()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const start = async () => {
    setBusy(true)
    setError(undefined)
    try {
      await api.scans.start(domain.domain_id)
      setStoredDomainId(domain.domain_id)
      navigate('/dashboard')
    } catch (err) {
      setError(errorText(err, '점검을 시작하지 못했습니다.'))
      setBusy(false)
    }
  }

  return (
    <VStack gap="x5">
      <HStack gap="x2" align="center">
        <Icon svg={<IconCheckmarkCircleFill />} color="fg.positive" size="x5" />
        <Text textStyle="t5Bold" color="fg.neutral">
          {`${domain.domain} 소유권이 확인됐습니다`}
        </Text>
      </HStack>
      <VStack gap="x2" p="x4" borderRadius="r3" bg="bg.neutralWeak">
        <Text textStyle="t3Bold" color="fg.neutralMuted">
          점검 범위와 안전 원칙
        </Text>
        {PRINCIPLES.map((p) => (
          <Text key={p} textStyle="t4Regular" color="fg.neutral">
            {`· ${p}`}
          </Text>
        ))}
      </VStack>
      {error && <Callout tone="critical" description={error} />}
      <ActionButton variant="brandSolid" size="large" loading={busy} onClick={start}>
        점검 시작
      </ActionButton>
    </VStack>
  )
}
