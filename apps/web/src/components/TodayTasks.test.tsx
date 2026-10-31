// 오늘 할 일: 서버가 정한 순서 그대로 보이고, 누르면 조치 가이드의 해당 카드로 가는지 확인한다.

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { TodayTask } from '../api/types'
import { TodayTasks } from './TodayTasks'

const TASKS: TodayTask[] = [
  { rank: 1, finding_id: 'F-0012', check_id: 16, title: '지원자 정보가 로그인 없이 보입니다', asset_alias: 'api', risk_score: 100, severity: 'critical', fix_minutes: 60, safety_score_after: 30, grade_after: 'F' },
  { rank: 2, finding_id: 'F-0007', check_id: 8, title: '누구나 내려받을 수 있는 지원자 백업 파일', asset_alias: 'www', risk_score: 93, severity: 'critical', fix_minutes: 10, safety_score_after: 49, grade_after: 'D' },
  { rank: 3, finding_id: 'F-0015', check_id: 18, title: '외부에서 열리는 채용 관리자 화면', asset_alias: 'admin', risk_score: 73, severity: 'high', fix_minutes: 30, safety_score_after: 100, grade_after: 'A' },
]

function ShowLocation() {
  const { pathname, hash } = useLocation()
  return <p>{`이동: ${pathname}${hash}`}</p>
}

function renderTasks(tasks = TASKS) {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/dashboard" element={<TodayTasks scanId="S-0001" tasks={tasks} currentScore={20} />} />
        <Route path="/guide/:scanId" element={<ShowLocation />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('TodayTasks', () => {
  it('서버가 정한 순서대로 제목과 등급을 보여 준다', () => {
    renderTasks()
    const titles = screen.getAllByText(/지원자|관리자/).map((el) => el.textContent)
    expect(titles).toEqual(TASKS.map((t) => t.title))
    expect(screen.getAllByText('긴급')).toHaveLength(2)
    expect(screen.getByText('높음')).toBeInTheDocument()
  })

  it('고치면 오를 점수를 직전 점수에서 이어서 보여 준다 (20 → 30, 30 → 49, 49 → 100)', () => {
    renderTasks()
    expect(screen.getByText('20 →')).toBeInTheDocument()
    expect(screen.getByText('30 →')).toBeInTheDocument()
    expect(screen.getByText('49 →')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('누르면 조치 가이드의 해당 카드(#task-N)로 이동한다', async () => {
    renderTasks()
    await userEvent.click(screen.getByText('누구나 내려받을 수 있는 지원자 백업 파일'))
    expect(screen.getByText('이동: /guide/S-0001#task-2')).toBeInTheDocument()
  })

  it('할 일이 없으면 빈 상태 문구를 보여 준다', () => {
    renderTasks([])
    expect(screen.getByText('오늘 할 일이 없습니다')).toBeInTheDocument()
  })
})
