// 점검 진행 띠 (정보 구조도 2장 공통 레이아웃). 어느 화면에서든 머리글 아래에 보인다.
// - 점검 중: 지금 단계, 진행 막대, 요청 예산, 중지 버튼(확인 대화상자)
// - 끝남: 새 안전 점수를 알리고 몇 초 뒤 사라진다
// 상태는 useScan()에서 받는다. 이 컴포넌트는 그리기만 한다.

import { IconCheckmarkCircleFill, IconExclamationmarkCircleFill } from '@karrotmarket/react-monochrome-icon'
import { Box, HStack, Text, VStack } from '@seed-design/react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { ActionButton } from 'seed-design/ui/action-button'
import {
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogRoot,
  AlertDialogTitle,
  AlertDialogTrigger,
} from 'seed-design/ui/alert-dialog'
import { PageBanner } from 'seed-design/ui/page-banner'
import { ProgressCircle } from 'seed-design/ui/progress-circle'
import { useScan } from '../hooks/useScan'
import { gradeStyle } from '../theme/severity'

const FINISHED_VISIBLE_MS = 8000

export function ScanBanner() {
  const { running, isRunning, lastFinished, error, stop, dismissFinished } = useScan()

  // 끝났다는 알림은 잠시 보여 주고 사라진다.
  useEffect(() => {
    if (!lastFinished) return
    const t = setTimeout(dismissFinished, FINISHED_VISIBLE_MS)
    return () => clearTimeout(t)
  }, [lastFinished, dismissFinished])

  const ratio = running && running.stage.total > 0 ? running.stage.done / running.stage.total : 0

  return (
    <AnimatePresence initial={false}>
      {isRunning && (
        <motion.div key="running" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
          <Box borderRadius="r4" overflowX="hidden" overflowY="hidden" borderWidth={1} borderColor="stroke.neutralSubtle" bg="bg.layerDefault">
            <HStack gap="x4" align="center" px="x5" py="x4" wrap>
              <ProgressCircle tone="brand" size="24" />
              <VStack gap="x0_5" grow>
                <Text textStyle="t5Bold" color="fg.neutral">
                  {`점검 중 · ${running?.stage.name ?? '준비 중'}`}
                </Text>
                <Text textStyle="t3Regular" color="fg.neutralMuted">
                  {running
                    ? `요청 ${running.budget.requests_used}건(최대 ${running.budget.requests_limit}건) · ${running.budget.elapsed_sec}초 경과 · 읽기 전용으로 점검합니다`
                    : '점검을 시작했습니다'}
                </Text>
              </VStack>
              <StopButton onConfirm={stop} />
            </HStack>
            {/* 진행 막대: 단계 안의 진행률. 단계 사이에는 브랜드 줄이 흐른다 */}
            <Box position="relative" height="3px" bg="bg.neutralWeak">
              <div className="a2d-flow-line" data-running="true" style={{ position: 'absolute', inset: 0, opacity: 0.35 }} />
              <motion.div
                style={{ position: 'absolute', inset: 0, transformOrigin: 'left', background: 'var(--seed-color-bg-brand-solid)' }}
                animate={{ scaleX: ratio }}
                transition={{ duration: 0.4 }}
              />
            </Box>
          </Box>
        </motion.div>
      )}

      {!isRunning && lastFinished && (
        <motion.div key="finished" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
          <PageBanner
            tone={lastFinished.status === 'failed' ? 'critical' : 'positive'}
            variant="weak"
            prefixIcon={lastFinished.status === 'failed' ? <IconExclamationmarkCircleFill /> : <IconCheckmarkCircleFill />}
            title={finishedTitle(lastFinished.status)}
            description={
              lastFinished.status === 'failed'
                ? (lastFinished.error_message ?? '잠시 뒤 다시 시도해 주세요.')
                : `안전 점수 ${lastFinished.safety_score}점 · ${lastFinished.grade} 등급(${lastFinished.grade ? gradeStyle[lastFinished.grade].caption : ''})`
            }
            style={{ borderRadius: 16 }}
          />
        </motion.div>
      )}

      {!isRunning && error && (
        <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <PageBanner tone="critical" variant="weak" prefixIcon={<IconExclamationmarkCircleFill />} description={error} style={{ borderRadius: 16 }} />
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function finishedTitle(status: string) {
  if (status === 'stopped') return '점검을 중지했습니다. 그때까지 모은 결과로 점수를 냈습니다'
  if (status === 'failed') return '점검이 실패했습니다'
  return '점검이 끝났습니다'
}

// 중지는 되돌릴 수 없어 한 번 더 묻는다.
function StopButton({ onConfirm }: { onConfirm: () => Promise<void> }) {
  return (
    <AlertDialogRoot>
      <AlertDialogTrigger asChild>
        <ActionButton variant="neutralWeak" size="small">
          중지
        </ActionButton>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>점검을 중지할까요?</AlertDialogTitle>
          <AlertDialogDescription>지금까지 모은 결과로 점수를 내고 점검을 멈춥니다.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <HStack gap="x2" justify="flex-end" width="full">
            <AlertDialogAction variant="neutralWeak">계속 점검</AlertDialogAction>
            <AlertDialogAction variant="criticalSolid" onClick={() => void onConfirm()}>
              중지
            </AlertDialogAction>
          </HStack>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialogRoot>
  )
}
