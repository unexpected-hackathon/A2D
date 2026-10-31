// 가짜 응답의 점수 계산이 docs/A2D_점검점수설계.md와 같은 값을 내는지 확인한다.

import { describe, expect, it } from 'vitest'
import { gradeOf, pickTodayTasks, riskRaw, safetyScore, severityOf } from './score'

describe('발견 위험 점수 (2.1 계산식)', () => {
  it('2.3 표의 값과 같다', () => {
    // #16 인증 없는 API, 개인정보 반환 (5,5,5,C5) → 100
    expect(Math.round(riskRaw({ e: 5, x: 5, d: 5, c: 5, confidence: 'confirmed' }))).toBe(100)
    // #8 백업 파일, www(C4) → 93
    expect(Math.round(riskRaw({ e: 5, x: 5, d: 5, c: 4, confidence: 'confirmed' }))).toBe(93)
    // #18 관리자 페이지 (5,3,4,C4) → 73
    expect(Math.round(riskRaw({ e: 5, x: 3, d: 4, c: 4, confidence: 'confirmed' }))).toBe(73)
    // #23 CVSS 9.0 이상, 가능성(0.8) → 65
    expect(Math.round(riskRaw({ e: 5, x: 4, d: 4, c: 4, confidence: 'likely' }))).toBe(65)
    // #30 보안 헤더 누락 → 30
    expect(Math.round(riskRaw({ e: 3, x: 2, d: 1, c: 4, confidence: 'confirmed' }))).toBe(30)
  })

  it('80·60·40을 기준으로 긴급·높음·중간·낮음으로 나눈다', () => {
    expect(severityOf(100)).toBe('critical')
    expect(severityOf(80)).toBe('critical')
    expect(severityOf(79.4)).toBe('high')
    expect(severityOf(60)).toBe('high')
    expect(severityOf(40)).toBe('medium')
    expect(severityOf(39)).toBe('low')
  })
})

describe('조직 안전 점수와 등급', () => {
  it('2.4 시나리오: 백업 파일 하나만 열리면 30 F', () => {
    expect(safetyScore([100])).toBe(30)
    expect(gradeOf(30)).toBe('F')
  })

  it('2.4 시나리오: 보안 헤더만 빠지면 79 B', () => {
    expect(safetyScore([30])).toBe(79)
    expect(gradeOf(79)).toBe('B')
  })

  it('발견이 없으면 100 A', () => {
    expect(safetyScore([])).toBe(100)
    expect(gradeOf(100)).toBe('A')
  })

  it('등급 경계: 90 A, 72 B, 58 C, 44 D, 그 아래 F', () => {
    expect([90, 89, 72, 71, 58, 57, 44, 43].map(gradeOf)).toEqual(['A', 'B', 'B', 'C', 'C', 'D', 'D', 'F'])
  })
})

describe('오늘 할 일 3가지 (FR-06)', () => {
  // target 기본 시연 프로필: #16(100) · #8(93.2) · #18(73.4)
  const findings = [
    { id: '#8', risk: riskRaw({ e: 5, x: 5, d: 5, c: 4, confidence: 'confirmed' }), fixMinutes: 10 },
    { id: '#18', risk: riskRaw({ e: 5, x: 3, d: 4, c: 4, confidence: 'confirmed' }), fixMinutes: 30 },
    { id: '#16', risk: riskRaw({ e: 5, x: 5, d: 5, c: 5, confidence: 'confirmed' }), fixMinutes: 60 },
  ]

  it('시작 점수는 20 F', () => {
    expect(safetyScore(findings.map((f) => f.risk))).toBe(20)
  })

  it('안전 점수가 가장 많이 오르는 순서로 고르고, 고친 뒤 점수는 30 → 49 → 100', () => {
    const picked = pickTodayTasks(findings)
    expect(picked.map((p) => p.finding.id)).toEqual(['#16', '#8', '#18'])
    expect(picked.map((p) => p.safetyAfter)).toEqual([30, 49, 100])
  })

  it('점수가 같으면 조치 시간이 짧은 것을 먼저 고른다', () => {
    const tie = [
      { id: 'slow', risk: 100, fixMinutes: 60 },
      { id: 'fast', risk: 100, fixMinutes: 10 },
    ]
    expect(pickTodayTasks(tie)[0].finding.id).toBe('fast')
  })
})
