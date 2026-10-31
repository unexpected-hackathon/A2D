import { describe, expect, it } from 'vitest'
import { formatDateTime, formatMinutes } from './format'

describe('formatMinutes', () => {
  it('한 시간 미만은 분, 넘으면 시간과 분으로', () => {
    expect(formatMinutes(10)).toBe('10분')
    expect(formatMinutes(60)).toBe('1시간')
    expect(formatMinutes(90)).toBe('1시간 30분')
  })
})

describe('formatDateTime', () => {
  it('한국 시간으로 월·일·시각을 보여 준다', () => {
    expect(formatDateTime('2026-10-31T14:07:40+09:00')).toBe('10월 31일 오후 2:07')
  })

  it('값이 없으면 빈 문자열', () => {
    expect(formatDateTime(null)).toBe('')
  })
})
