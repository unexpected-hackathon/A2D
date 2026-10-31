// 4-5 요약 내보내기 (FR-13, P1). 기록 화면에서 모달로 띄운다.
// 별도 API 없이 GET /domains/{id}/summary 하나로 안전 점수 게이지와 등급별 발견 수를 보여 주고,
// 브라우저 인쇄(PDF로 저장)로 내보낸다(API 명세 2장).
//
// 인쇄: 모달은 화면 위에 떠 있어 그대로 인쇄하면 뒤 화면까지 찍힌다. 그래서 같은 요약을
// body 바로 아래(a2d-print-only)에 한 벌 더 그려 두고, 인쇄할 때는 그것만 보이게 한다(global.css).

import { IconDocumentArrowLeftLine } from '@karrotmarket/react-monochrome-icon'
import { HStack, PrefixIcon, Text, VStack } from '@seed-design/react'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { ActionButton } from 'seed-design/ui/action-button'
import { Callout } from 'seed-design/ui/callout'
import { DialogBody, DialogContent, DialogFooter, DialogRoot, DialogTrigger } from 'seed-design/ui/dialog'
import type { Severity, Summary } from '../api/types'
import { api } from '../api/endpoints'
import logoUrl from '../assets/a2d-logo.svg'
import { useApi } from '../hooks/useApi'
import { formatDateTime } from '../lib/format'
import { severityStyle } from '../theme/severity'
import { GradeBadge } from './Badges'
import { ScoreGauge } from './ScoreGauge'

const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low']

export function ExportDialog({ domainId }: { domainId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <DialogRoot open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <ActionButton variant="neutralWeak">
          <PrefixIcon svg={<IconDocumentArrowLeftLine />} />요약 내보내기
        </ActionButton>
      </DialogTrigger>
      <DialogContent title="요약" style={{ maxWidth: 640, width: 'calc(100% - 32px)' }}>
        <ExportBody domainId={domainId} />
      </DialogContent>
    </DialogRoot>
  )
}

// 모달이 열릴 때만 그려진다(SEED Dialog는 닫히면 내용을 내린다). 그래서 열 때마다 최신 요약을 부른다.
function ExportBody({ domainId }: { domainId: string }) {
  const summary = useApi(() => api.domains.summary(domainId), [domainId])
  const s = summary.data

  return (
    <>
      <DialogBody>
        {summary.error ? (
          <Callout
            tone="critical"
            title="요약을 만들지 못했습니다"
            description={summary.error.message}
            linkProps={{ children: '다시 시도', onClick: () => void summary.reload() }}
          />
        ) : !s ? (
          <Text textStyle="t5Regular" color="fg.neutralMuted">
            불러오는 중…
          </Text>
        ) : (
          <>
            <OnePager s={s} />
            {createPortal(
              <div className="a2d-print-only">
                <OnePager s={s} />
              </div>,
              document.body,
            )}
          </>
        )}
      </DialogBody>
      <DialogFooter>
        <HStack gap="x2" justify="flex-end" width="full">
          <ActionButton variant="brandSolid" onClick={() => window.print()} disabled={!s}>
            인쇄 · PDF로 저장
          </ActionButton>
        </HStack>
      </DialogFooter>
    </>
  )
}

function OnePager({ s }: { s: Summary }) {
  return (
    <VStack gap="x6" className="a2d-onepager">
      <HStack justify="space-between" align="center">
        <img src={logoUrl} alt="A2D" height={32} />
        <VStack align="flex-end" gap="x0_5">
          <Text textStyle="t5Bold" color="fg.neutral">
            {s.domain}
          </Text>
          <Text textStyle="t3Regular" color="fg.neutralSubtle">
            {s.latest_scan ? `${formatDateTime(s.latest_scan.finished_at)} 점검` : '점검 전'}
          </Text>
        </VStack>
      </HStack>

      {/* 전체 점수 */}
      <VStack gap="x3">
        <HStack gap="x3" align="center">
          <Text textStyle="t3Bold" color="fg.neutralMuted">
            안전 점수
          </Text>
          <Text textStyle="t10Bold" color="fg.neutral">
            {s.safety_score}
          </Text>
          <GradeBadge grade={s.grade} size="large" />
        </HStack>
        <ScoreGauge score={s.safety_score} grade={s.grade} />
      </VStack>

      {/* 등급별 발견 수 */}
      <VStack gap="x3">
        <Text textStyle="t4Bold" color="fg.neutral">
          등급별 발견 수
        </Text>
        <div className="a2d-counts">
          {SEVERITY_ORDER.map((sev) => (
            <VStack key={sev} gap="x0_5" px="x3" py="x2" borderRadius="r3" bg="bg.neutralWeak">
              <Text textStyle="t2Medium" color="fg.neutralSubtle">
                {severityStyle[sev].label}
              </Text>
              <Text textStyle="t6Bold" color={s.counts[sev] ? 'fg.neutral' : 'fg.neutralSubtle'}>
                {s.counts[sev]}
              </Text>
            </VStack>
          ))}
        </div>
      </VStack>

      <Text textStyle="t2Regular" color="fg.neutralSubtle">
        A2D는 소유권을 증명한 도메인만 읽기 전용으로 점검합니다. 점수 계산식과 근거는 A2D 화면의 기술 근거에서 볼 수 있습니다.
      </Text>
    </VStack>
  )
}
