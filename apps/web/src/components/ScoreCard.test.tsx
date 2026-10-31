// 점수 카드: 점수·등급을 읽을 수 있게 보여 주고, 재점검 버튼과 산식 펼치기가 동작하는지 확인한다.

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LazyMotion, domAnimation } from 'motion/react'
import { describe, expect, it, vi } from 'vitest'
import type { Summary } from '../api/types'
import { ScoreCard } from './ScoreCard'

const SUMMARY: Summary = {
  domain_id: 'DOM-1',
  domain: 'jobnest.test',
  latest_scan: { scan_id: 'S-0001', finished_at: '2026-10-31T14:07:40+09:00', status: 'done' },
  running_scan_id: null,
  safety_score: 20,
  grade: 'F',
  org_risk_score: 80,
  score_formula: '0.7 × 100 + 0.3 × (93 + 73) ÷ 5 = 80',
  counts: { critical: 2, high: 1, medium: 0, low: 0, info: 0 },
  asset_count: 7,
  today_tasks: [],
  alerts: [],
}

function renderCard(props: Partial<{ onRescan: () => void; scanning: boolean }> = {}) {
  const onRescan = props.onRescan ?? vi.fn()
  render(
    <LazyMotion features={domAnimation}>
      <ScoreCard summary={SUMMARY} onRescan={onRescan} scanning={props.scanning ?? false} />
    </LazyMotion>,
  )
  return { onRescan }
}

describe('ScoreCard', () => {
  it('점수와 등급을 화면 읽기 프로그램도 읽을 수 있게 붙인다', () => {
    renderCard()
    expect(screen.getByLabelText('안전 점수 20점, F 등급')).toBeInTheDocument()
    expect(screen.getByText('F · 위험')).toBeInTheDocument()
  })

  it('등급별 발견 수를 보여 준다', () => {
    renderCard()
    expect(screen.getByText('긴급').nextSibling).toHaveTextContent('2')
    expect(screen.getByText('높음').nextSibling).toHaveTextContent('1')
  })

  it('재점검 버튼을 누르면 onRescan을 부른다', async () => {
    const { onRescan } = renderCard()
    await userEvent.click(screen.getByRole('button', { name: '재점검' }))
    expect(onRescan).toHaveBeenCalledOnce()
  })

  it('점검 중이면 버튼 글자가 "점검 중"으로 바뀐다', () => {
    renderCard({ scanning: true })
    expect(screen.getByRole('button', { name: /점검 중/ })).toBeInTheDocument()
  })

  it('"산식 보기"를 누르면 조직 위험 산식과 안전 점수 계산이 보인다', async () => {
    renderCard()
    await userEvent.click(screen.getByRole('button', { name: '산식 보기' }))
    expect(screen.getByText(/조직 위험 0\.7 × 100.*안전 점수 100 − 80 = 20/)).toBeInTheDocument()
  })
})
