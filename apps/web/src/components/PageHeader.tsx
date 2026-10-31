// 각 화면 맨 위의 제목 영역. 이름표(eyebrow) · 제목 · 설명 · 오른쪽 버튼 자리.

import { HStack, Text, VStack } from '@seed-design/react'
import type { ReactNode } from 'react'

interface PageHeaderProps {
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <HStack justify="space-between" align="flex-end" gap="x4" wrap>
      <VStack gap="x1_5">
        {eyebrow && (
          <Text textStyle="t3Bold" color="fg.brand">
            {eyebrow}
          </Text>
        )}
        <Text as="h1" textStyle="t10Bold" color="fg.neutral">
          {title}
        </Text>
        {description && (
          <Text as="p" textStyle="t5Regular" color="fg.neutralMuted">
            {description}
          </Text>
        )}
      </VStack>
      {actions && <HStack gap="x2">{actions}</HStack>}
    </HStack>
  )
}
