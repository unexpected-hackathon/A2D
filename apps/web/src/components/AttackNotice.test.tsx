// 추가 점검 알림: 서버 문장이 있을 때만, 상태에 맞는 제목으로 보이는지 확인한다.

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { AttackState } from '../api/types'
import { attackNotice } from '../lib/attackNotice'
import { AttackNotice } from './AttackNotice'

const SKIPPED: AttackState = {
  status: 'skipped',
  reason: 'llm_not_configured',
  message: 'AI 서버가 연결되지 않아 추가 점검을 건너뛰었습니다. 기본 점검 결과로 점수를 냈습니다.',
}

describe('AttackNotice', () => {
  it('건너뛰었으면 제목과 서버 문장을 보여 준다', () => {
    render(<AttackNotice attack={SKIPPED} />)
    expect(screen.getByText('추가 점검 건너뜀')).toBeInTheDocument()
    expect(screen.getByText(SKIPPED.message!)).toBeInTheDocument()
  })

  it('일부만 확인했거나 실패하면 그에 맞는 제목을 고른다', () => {
    expect(attackNotice({ status: 'done', reason: 'llm_interrupted', message: '일부만 확인했습니다.' })?.title).toBe(
      '추가 점검 일부만 확인',
    )
    expect(attackNotice({ status: 'failed', reason: 'error', message: '오류가 났습니다.' })?.title).toBe('추가 점검 실패')
  })

  it('정상으로 끝났거나 필드가 없으면 아무것도 보이지 않는다', () => {
    expect(attackNotice({ status: 'done', reason: null, message: null })).toBeNull()
    expect(attackNotice(null)).toBeNull()
    expect(attackNotice(undefined)).toBeNull()
    const { container } = render(<AttackNotice attack={{ status: 'skipped', reason: null, message: null }} />)
    expect(container).toBeEmptyDOMElement()
  })
})
