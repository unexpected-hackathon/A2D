// 추가 점검 상태 → 대시보드 알림의 제목과 문장. 문장은 서버가 정한다(API 명세 GET /scans/{scan_id}의 attack.message).
// 화면은 상태에 맞는 제목만 고른다. 문장이 없으면(정상 완료, 예전 점검) 알리지 않는다.

import type { AttackState } from '../api/types'

export function attackNotice(attack: AttackState | null | undefined): { title: string; description: string } | null {
  if (!attack?.message) return null
  if (attack.status === 'skipped') return { title: '추가 점검 건너뜀', description: attack.message }
  if (attack.status === 'failed') return { title: '추가 점검 실패', description: attack.message }
  if (attack.status === 'done') return { title: '추가 점검 일부만 확인', description: attack.message }
  return null
}
