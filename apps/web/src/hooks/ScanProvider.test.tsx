// 점검 상태: 이미 진행 중인 점검을 찾다가 실패해도 처리되지 않은 오류 없이 안내 문구로 바뀌는지 확인한다.

import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { api } from '../api/endpoints'
import { ScanProvider } from './ScanProvider'
import { useScan } from './useScan'

afterEach(() => vi.restoreAllMocks())

function Probe() {
  const scan = useScan()
  return (
    <div>
      <button type="button" onClick={() => void scan.start()}>
        시작
      </button>
      <p>{scan.error ?? '오류 없음'}</p>
    </div>
  )
}

describe('ScanProvider.start', () => {
  it('SCAN_IN_PROGRESS 뒤 요약 요청까지 실패하면 오류 문구로 알린다', async () => {
    const summary = vi.spyOn(api.domains, 'summary').mockRejectedValue(new ApiError(500, 'UNKNOWN', '서버 오류'))
    vi.spyOn(api.scans, 'start').mockRejectedValue(new ApiError(409, 'SCAN_IN_PROGRESS', '이미 진행 중인 점검이 있습니다.'))

    render(
      <ScanProvider domainId="DOM-1">
        <Probe />
      </ScanProvider>,
    )
    await act(async () => {
      screen.getByRole('button', { name: '시작' }).click()
    })

    expect(await screen.findByText('진행 중인 점검을 찾지 못했습니다. 잠시 뒤 다시 시도해 주세요.')).toBeInTheDocument()
    expect(summary).toHaveBeenCalled()
  })

  it('시작 자체가 실패하면 서버 문구를 그대로 보여 준다', async () => {
    vi.spyOn(api.domains, 'summary').mockResolvedValue({ running_scan_id: null } as never)
    vi.spyOn(api.scans, 'start').mockRejectedValue(new ApiError(409, 'DOMAIN_NOT_VERIFIED', '도메인 소유권이 확인되지 않아 점검을 시작할 수 없습니다.'))

    render(
      <ScanProvider domainId="DOM-1">
        <Probe />
      </ScanProvider>,
    )
    await act(async () => {
      screen.getByRole('button', { name: '시작' }).click()
    })

    expect(await screen.findByText('도메인 소유권이 확인되지 않아 점검을 시작할 수 없습니다.')).toBeInTheDocument()
  })
})
