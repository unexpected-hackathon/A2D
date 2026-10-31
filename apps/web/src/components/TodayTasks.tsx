// 2-2 오늘 할 일 3가지.
// 순서는 서버(코드)가 정한 그대로 보여 준다(FR-06). 누르면 조치 가이드의 해당 카드로 간다.

import { IconChevronRightLine } from '@karrotmarket/react-monochrome-icon'
import { HStack, Icon, Text, VStack } from '@seed-design/react'
import { motion, useReducedMotion } from 'motion/react'
import { useNavigate } from 'react-router-dom'
import { ResultSection } from 'seed-design/ui/result-section'
import type { TodayTask } from '../api/types'
import { formatMinutes } from '../lib/format'
import { gradeStyle } from '../theme/severity'
import { SeverityBadge } from './Badges'
import { Surface } from './Surface'

interface TodayTasksProps {
  scanId: string
  tasks: TodayTask[]
  currentScore: number
}

export function TodayTasks({ scanId, tasks, currentScore }: TodayTasksProps) {
  const navigate = useNavigate()
  const reduce = useReducedMotion()

  return (
    <Surface>
      <VStack gap="x4">
        <HStack justify="space-between" align="flex-end" gap="x2" wrap>
          <Text textStyle="t5Bold" color="fg.neutral">
            오늘 할 일 3가지
          </Text>
          <Text textStyle="t3Regular" color="fg.neutralSubtle">
            고쳤을 때 점수가 가장 많이 오르는 순서
          </Text>
        </HStack>

        {tasks.length === 0 ? (
          <ResultSection size="medium" title="오늘 할 일이 없습니다" description="새로 고칠 문제가 없습니다. 내일 다시 점검합니다." />
        ) : (
          <VStack gap="x2">
            {tasks.map((task, i) => {
              const before = i === 0 ? currentScore : tasks[i - 1].safety_score_after
              return (
                <motion.button
                  key={task.finding_id}
                  type="button"
                  onClick={() => navigate(`/guide/${scanId}#task-${task.rank}`)}
                  initial={reduce ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.08 * i, duration: 0.3 }}
                  whileHover={reduce ? undefined : { y: -1 }}
                  className="a2d-task"
                >
                  <div className="a2d-task-grid">
                    {/* 순서 번호 */}
                    <VStack
                      align="center"
                      justify="center"
                      width="36px"
                      height="36px"
                      borderRadius="full"
                      bg={i === 0 ? 'bg.brandSolid' : 'bg.brandWeak'}
                      flexShrink={0}
                    >
                      <Text textStyle="t5Bold" color={i === 0 ? 'fg.onBrandSolid' : 'fg.brandContrast'}>
                        {task.rank}
                      </Text>
                    </VStack>

                    <VStack gap="x1" className="a2d-task-main">
                      <HStack gap="x2" align="center" wrap>
                        <SeverityBadge severity={task.severity} />
                        <Text textStyle="t5Bold" color="fg.neutral">
                          {task.title}
                        </Text>
                      </HStack>
                      <Text textStyle="t3Regular" color="fg.neutralMuted">
                        {`${task.asset_alias} · #${task.check_id} · 조치 약 ${formatMinutes(task.fix_minutes)}`}
                      </Text>
                    </VStack>

                    {/* 고치면 안전 점수가 어떻게 바뀌는지 */}
                    <VStack gap="x0_5" className="a2d-task-score">
                      <Text textStyle="t2Medium" color="fg.neutralSubtle">
                        고치면
                      </Text>
                      <HStack gap="x1" align="flex-end">
                        <Text textStyle="t3Regular" color="fg.neutralSubtle">
                          {before} →
                        </Text>
                        <Text textStyle="t6Bold" color="fg.positive">
                          {task.safety_score_after}
                        </Text>
                        <Text textStyle="t3Bold" color="fg.neutralMuted">
                          {`${task.grade_after}`}
                        </Text>
                      </HStack>
                      <Text textStyle="t2Regular" color="fg.neutralSubtle">
                        {gradeStyle[task.grade_after].caption}
                      </Text>
                    </VStack>
                    <Icon svg={<IconChevronRightLine />} color="fg.neutralSubtle" size="x4" />
                  </div>
                </motion.button>
              )
            })}
          </VStack>
        )}
      </VStack>
    </Surface>
  )
}
