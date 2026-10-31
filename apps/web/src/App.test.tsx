// 앱 전체를 가짜 응답으로 띄워 화면 사이 흐름을 확인하는 통합 테스트.
// 가짜 서버는 메모리에 상태를 두므로 테스트마다 모듈을 새로 불러 처음 상태에서 시작한다.

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LazyMotion, domAnimation } from 'motion/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const TIMEOUT = { timeout: 4000 }

async function renderApp(path: string) {
  const { default: App } = await import('./App')
  render(
    <LazyMotion features={domAnimation}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </LazyMotion>,
  )
}

beforeEach(() => {
  vi.resetModules()
})

describe('대시보드', () => {
  it('안전 점수 20 F와 오늘 할 일 3가지, 발견 3건을 보여 준다', async () => {
    await renderApp('/dashboard')
    expect(await screen.findByLabelText('안전 점수 20점, F 등급', {}, TIMEOUT)).toBeInTheDocument()
    expect(screen.getByText('지원자 정보가 로그인 없이 보입니다')).toBeInTheDocument()
    expect(await screen.findByText('인증 없는 API', {}, TIMEOUT)).toBeInTheDocument()
    expect(screen.getByText('발견')).toBeInTheDocument()
  })

  it('발견을 누르면 기술 근거 패널에 산식이 보인다', async () => {
    await renderApp('/dashboard')
    await userEvent.click(await screen.findByText('인증 없는 API', {}, TIMEOUT))
    expect(await screen.findByText('기술 근거', {}, TIMEOUT)).toBeInTheDocument()
    expect(await screen.findByText(/100 × \(\(5 × 5 × 5 × 5\)/, {}, TIMEOUT)).toBeInTheDocument()
  })
})

describe('조치 가이드', () => {
  it('근거 검증 표시와 카드 3장을 보여 준다', async () => {
    await renderApp('/guide/S-0001')
    expect(await screen.findByText('근거 검증 통과 3/3', {}, TIMEOUT)).toBeInTheDocument()
    expect(screen.getAllByText('기술 근거 보기')).toHaveLength(3)
  })

  it('근거 없는 질문에는 답하지 않는다', async () => {
    await renderApp('/guide/S-0001')
    const box = await screen.findByPlaceholderText('예: 백업 파일은 왜 위험해요?', {}, TIMEOUT)
    await userEvent.type(box, '오늘 날씨 어때요?')
    await userEvent.click(screen.getByRole('button', { name: '질문하기' }))
    expect(await screen.findByText('이번 점검 결과로는 답할 근거가 없습니다.', {}, TIMEOUT)).toBeInTheDocument()
  })
})

describe('로그인', () => {
  it('비밀번호가 틀리면 오류 문구를 보여 준다', async () => {
    await renderApp('/login')
    await userEvent.type(screen.getByLabelText('이메일'), 'admin@jobnest.test')
    await userEvent.type(screen.getByLabelText('비밀번호'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: '로그인' }))
    expect(await screen.findByText('이메일 또는 비밀번호가 맞지 않습니다.', {}, TIMEOUT)).toBeInTheDocument()
  })

  it('맞으면 도메인이 있으니 대시보드로 간다', async () => {
    await renderApp('/login')
    await userEvent.type(screen.getByLabelText('이메일'), 'admin@jobnest.test')
    await userEvent.type(screen.getByLabelText('비밀번호'), 'a2d-demo')
    await userEvent.click(screen.getByRole('button', { name: '로그인' }))
    expect(await screen.findByText('오늘의 외부 노출 상태', {}, TIMEOUT)).toBeInTheDocument()
  })
})

describe('기록', () => {
  it('첫 점검 하나의 점수 추이와 변화를 보여 준다', async () => {
    await renderApp('/history')
    expect(await screen.findByRole('img', { name: /S-0001 20점/ }, TIMEOUT)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('첫 점검이라 비교할 직전 점검이 없습니다.')).toBeInTheDocument(), TIMEOUT)
  })
})
