// 개발용: API 모듈과 가짜 응답이 제대로 도는지 버튼으로 확인하는 화면 (/dev/api).
// 화면 개발에는 쓰지 않는다. 메뉴에도 없고 주소로만 들어온다.

import { HStack, Text, VStack } from '@seed-design/react'
import { useState } from 'react'
import { ActionButton } from 'seed-design/ui/action-button'
import { Badge } from 'seed-design/ui/badge'
import { ApiError, USE_MOCK } from '../api/client'
import { api } from '../api/endpoints'
import { PageHeader } from '../components/PageHeader'
import { Surface } from '../components/Surface'
import { useDomain } from '../hooks/useDomain'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function DevApiPage() {
  const domainId = useDomain().domain.domain_id
  const [log, setLog] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const write = (line: string) => setLog((prev) => [...prev, line])

  // 요청 하나를 보내고 결과를 기록에 남긴다.
  const call = async (label: string, run: () => Promise<unknown>) => {
    write(`→ ${label}`)
    try {
      const result = await run()
      write(JSON.stringify(result, null, 2) ?? '(본문 없음)')
      return result
    } catch (e) {
      const err = e as ApiError
      write(`✕ ${err.status} ${err.code}: ${err.message}`)
      return undefined
    }
  }

  // 재점검 시나리오: 점검 시작 → 끝날 때까지 상태 확인 → 요약에서 점수 확인
  const runRescan = async () => {
    setBusy(true)
    setLog([])
    const started = (await call('POST /domains/{id}/scans', () => api.scans.start(domainId))) as
      | { scan_id: string }
      | undefined
    if (started) {
      for (;;) {
        await sleep(1000)
        const scan = await api.scans.get(started.scan_id)
        write(`  ${scan.scan_id} · ${scan.stage.name} (${scan.stage.done}/${scan.stage.total})`)
        if (scan.status === 'done' || scan.status === 'stopped') break
      }
      const summary = await api.domains.summary(domainId)
      write(`✓ 안전 점수 ${summary.safety_score} (${summary.grade}) · 오늘 할 일 ${summary.today_tasks.length}개`)
    }
    setBusy(false)
  }

  const quick: [string, () => Promise<unknown>][] = [
    ['GET /auth/me', () => api.auth.me()],
    ['GET /health', () => api.health()],
    ['GET /domains/{id}/summary', () => api.domains.summary(domainId)],
    ['GET /domains/{id}/history', () => api.domains.history(domainId)],
    ['GET /scans/S-0001/findings', () => api.scans.findings('S-0001')],
    ['GET /findings/F-0012', () => api.findings.get('F-0012')],
    ['GET /scans/S-0001/report', () => api.scans.guide('S-0001')],
  ]

  return (
    <VStack gap="x6">
      <PageHeader
        eyebrow="개발용"
        title="API 확인"
        description="API 모듈이 어떤 응답을 돌려주는지 버튼으로 확인합니다."
        actions={
          <Badge tone={USE_MOCK ? 'warning' : 'positive'} variant="weak" size="large">
            {USE_MOCK ? '가짜 응답' : '실제 서버'}
          </Badge>
        }
      />
      <Surface>
        <VStack gap="x4">
          <Text textStyle="t5Bold">재점검 시나리오</Text>
          <Text textStyle="t4Regular" color="fg.neutralMuted">
            누를 때마다 오늘 할 일 1번을 고쳤다고 보고 점검합니다. 안전 점수가 20 → 30 → 49 → 100으로 오릅니다.
          </Text>
          <HStack>
            <ActionButton variant="brandSolid" loading={busy} onClick={runRescan}>
              재점검 실행
            </ActionButton>
          </HStack>
        </VStack>
      </Surface>
      <Surface>
        <VStack gap="x3">
          <Text textStyle="t5Bold">요청 하나씩 보내기</Text>
          <HStack gap="x2" wrap>
            {quick.map(([label, run]) => (
              <ActionButton
                key={label}
                variant="neutralWeak"
                size="small"
                onClick={() => {
                  setLog([])
                  void call(label, run)
                }}
              >
                {label}
              </ActionButton>
            ))}
          </HStack>
        </VStack>
      </Surface>
      <Surface p="x0">
        <pre
          style={{
            margin: 0,
            padding: 20,
            maxHeight: 480,
            overflow: 'auto',
            fontSize: 12.5,
            lineHeight: 1.6,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            color: 'var(--seed-color-fg-neutral)',
          }}
        >
          {log.length ? log.join('\n') : '버튼을 누르면 응답이 여기에 나옵니다.'}
        </pre>
      </Surface>
    </VStack>
  )
}
