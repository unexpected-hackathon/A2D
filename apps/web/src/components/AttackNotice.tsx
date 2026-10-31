// 추가 점검(Attack 에이전트, FR-04)을 건너뛰었거나 일부만 했을 때 대시보드에 한 줄로 알린다.
// 건너뜀은 정상 동작이라(기본 점검으로 점수는 나온다) 경고색이 아니라 중립색으로 보인다.

import { Callout } from 'seed-design/ui/callout'
import type { AttackState } from '../api/types'
import { attackNotice } from '../lib/attackNotice'

export function AttackNotice({ attack }: { attack: AttackState | null | undefined }) {
  const notice = attackNotice(attack)
  if (!notice) return null
  return <Callout tone="neutral" title={notice.title} description={notice.description} />
}
