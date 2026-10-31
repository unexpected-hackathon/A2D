// 각 화면 맨 위의 제목 영역. 이름표(eyebrow) · 제목 · 설명 · 오른쪽 버튼 자리.
// 내용 영역의 바탕색(종이 색)에 따라 글자색이 달라져야 해서 SEED Text 대신 CSS 변수(--a2d-ink)를 쓴다.

import { HStack } from '@seed-design/react'
import type { ReactNode } from 'react'

interface PageHeaderProps {
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <HStack justify="space-between" align="flex-end" gap="x4" wrap className="a2d-ph">
      <div className="a2d-ph__text">
        {eyebrow && <p className="a2d-ph__eyebrow">{eyebrow}</p>}
        <h1 className="a2d-ph__title">{title}</h1>
        {description && <p className="a2d-ph__desc">{description}</p>}
      </div>
      {actions && <HStack gap="x2">{actions}</HStack>}
    </HStack>
  )
}
