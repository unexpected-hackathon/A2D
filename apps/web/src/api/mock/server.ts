// 가짜 서버. client.ts가 VITE_USE_MOCK일 때 fetch 대신 이 함수를 부른다.
// API 명세와 같은 주소·응답 모양을 돌려주고, 상태는 메모리에만 둔다(새로고침하면 처음으로).
//
// 시연 흐름 흉내: 재점검할 때마다 "오늘 할 일" 1번을 담당자가 고쳤다고 보고 그 발견을 뺀다.
// 그래서 안전 점수가 20 → 30 → 49 → 100으로 오른다.

import type {
  Alert,
  Asset,
  AuditEntry,
  ChangedFinding,
  Domain,
  FindingDetail,
  FindingSummary,
  Grade,
  Guide,
  Scan,
  ScanStatus,
  Severity,
  Summary,
} from '../types'
import { ASSETS, CHECKS, DEMO_DOMAIN, DEMO_PASSWORD, DEMO_USER, FINDINGS, TEST_ASSET, TEST_FINDING, checkName, type FindingSeed } from './data'
import {
  confidenceFactor,
  gradeOf,
  orgRiskRaw,
  pickTodayTasks,
  riskFormula,
  riskRaw,
  safetyScore,
  severityOf,
  type Factors,
} from './score'

type Method = 'GET' | 'POST' | 'PATCH'
interface MockResponse {
  status: number
  data?: unknown
}

// ---------------------------------------------------------------------------
// 상태
// ---------------------------------------------------------------------------

interface MockScan {
  scan_id: string
  domain_id: string
  startedAt: number
  stoppedAt: number | null
  openFindingIds: string[] // 이 점검에서 발견된 것
  previous_scan_id: string | null
  testServerOpen: boolean // 감시 시연: 새 테스트 서버가 열렸나
}

// 점검 단계와 걸리는 시간(ms). 합계 약 9초.
const STAGES: { status: ScanStatus; name: string; ms: number }[] = [
  { status: 'queued', name: '대기 중', ms: 600 },
  { status: 'discovering', name: '자산 찾는 중', ms: 1800 },
  { status: 'checking', name: '기본 점검 중', ms: 2600 },
  { status: 'agent', name: '추가 점검 중', ms: 1800 },
  { status: 'scoring', name: '점수 계산 중', ms: 900 },
  { status: 'reporting', name: '조치 가이드 작성 중', ms: 1200 },
]
const TOTAL_MS = STAGES.reduce((sum, s) => sum + s.ms, 0)
// 단계별로 보여 줄 "하는 일 수" (진행 막대용)
const STAGE_TOTAL: Partial<Record<ScanStatus, number>> = { discovering: 5, checking: 24, agent: 9 }

const FIXED_IMPORTANCE_CHECKS = new Set([6, 12, 14, 32, 33, 34])
const FIXED_IMPORTANCE: Record<number, number> = { 6: 4, 12: 5, 14: 5, 32: 5, 33: 5, 34: 5 }

const now = Date.now()
const state = {
  loggedIn: true, // 4단계(로그인) 전까지는 로그인된 상태로 시작한다.
  failedLogins: 0,
  lockedUntil: 0,
  domains: new Map<string, Domain>([
    [
      'DOM-1',
      {
        domain_id: 'DOM-1',
        domain: DEMO_DOMAIN,
        verify_status: 'verified',
        txt_record: { name: `_a2d-verify.${DEMO_DOMAIN}`, value: 'a2d-verify=7f3c9e21b4d84a6c' },
        verified_at: new Date(now - 30 * 60_000).toISOString(),
        created_at: new Date(now - 32 * 60_000).toISOString(),
      },
    ],
  ]),
  scans: [
    {
      scan_id: 'S-0001',
      domain_id: 'DOM-1',
      startedAt: now - 20 * 60_000,
      stoppedAt: null,
      openFindingIds: FINDINGS.map((f) => f.finding_id),
      previous_scan_id: null,
      testServerOpen: false,
    },
  ] as MockScan[],
  importanceOverride: new Map<string, number>(), // asset_id → 1~5
}

// ---------------------------------------------------------------------------
// 계산 도우미
// ---------------------------------------------------------------------------

const kst = (ms: number) => {
  const d = new Date(ms + 9 * 3600_000)
  return d.toISOString().replace('Z', '+09:00').replace(/\.\d{3}/, '')
}

function scanStatus(scan: MockScan): { status: ScanStatus; stageName: string; done: number; total: number; finishedAt: number | null } {
  if (scan.stoppedAt !== null) {
    return { status: 'stopped', stageName: '중지됨', done: 0, total: 0, finishedAt: scan.stoppedAt }
  }
  let elapsed = Date.now() - scan.startedAt
  for (const stage of STAGES) {
    if (elapsed < stage.ms) {
      const total = STAGE_TOTAL[stage.status] ?? 1
      return {
        status: stage.status,
        stageName: stage.name,
        done: Math.min(total, Math.floor((elapsed / stage.ms) * total)),
        total,
        finishedAt: null,
      }
    }
    elapsed -= stage.ms
  }
  return { status: 'done', stageName: '완료', done: 1, total: 1, finishedAt: scan.startedAt + TOTAL_MS }
}

const isFinished = (scan: MockScan) => ['done', 'stopped'].includes(scanStatus(scan).status)

function importanceOf(assetId: string) {
  const seed = ALL_ASSETS.find((a) => a.asset_id === assetId)!
  const override = state.importanceOverride.get(assetId)
  return override === undefined
    ? seed.importance
    : { value: override, source: 'manual' as const, rule: null }
}

function factorsOf(f: FindingSeed): Factors {
  const fixed = FIXED_IMPORTANCE_CHECKS.has(f.check_id)
  return {
    e: f.e,
    x: f.x,
    d: f.d,
    c: fixed ? FIXED_IMPORTANCE[f.check_id] : importanceOf(f.asset_id).value,
    confidence: f.confidence,
  }
}

const ALL_FINDINGS = [...FINDINGS, TEST_FINDING]
const ALL_ASSETS = [...ASSETS, TEST_ASSET]
const seedOf = (id: string) => ALL_FINDINGS.find((f) => f.finding_id === id)!
const aliasOf = (assetId: string) => ALL_ASSETS.find((a) => a.asset_id === assetId)!.alias
// 테스트 서버는 그 점검에서 열려 있을 때만 자산 목록에 나온다.
const assetsOf = (scan: MockScan) => (scan.testServerOpen ? ALL_ASSETS : ASSETS)

function scoredFindings(scan: MockScan) {
  return scan.openFindingIds.map((id) => {
    const seed = seedOf(id)
    const risk = riskRaw(factorsOf(seed))
    return { id, seed, risk, fixMinutes: seed.fix_minutes }
  })
}

function scanScore(scan: MockScan): { safety: number; grade: Grade; orgRisk: number } {
  const risks = scoredFindings(scan).map((f) => f.risk)
  const safety = safetyScore(risks)
  return { safety, grade: gradeOf(safety), orgRisk: Math.round(orgRiskRaw(risks)) }
}

function firstSeenScanId(findingId: string, upTo: MockScan): string {
  const scans = state.scans.filter((s) => s.domain_id === upTo.domain_id)
  const index = scans.indexOf(upTo)
  let first = upTo.scan_id
  for (let i = index; i >= 0; i--) {
    if (scans[i].openFindingIds.includes(findingId)) first = scans[i].scan_id
    else break
  }
  return first
}

function findingSummary(scan: MockScan, id: string): FindingSummary {
  const seed = seedOf(id)
  const risk = riskRaw(factorsOf(seed))
  const first = firstSeenScanId(id, scan)
  return {
    finding_id: id,
    check_id: seed.check_id,
    check_name: checkName(seed.check_id),
    asset_id: seed.asset_id,
    asset_alias: aliasOf(seed.asset_id),
    situation: seed.situation,
    risk_score: Math.round(risk),
    severity: severityOf(risk),
    confidence: seed.confidence,
    status: first === scan.scan_id && scan.previous_scan_id ? 'new' : 'open',
    first_seen_scan_id: first,
  }
}

const latestFinishedScan = (domainId: string) =>
  [...state.scans].reverse().find((s) => s.domain_id === domainId && isFinished(s)) ?? null
const runningScan = (domainId: string) =>
  state.scans.find((s) => s.domain_id === domainId && !isFinished(s)) ?? null
const findScan = (scanId: string) => state.scans.find((s) => s.scan_id === scanId)

function scanResponse(scan: MockScan): Scan {
  const st = scanStatus(scan)
  const finished = st.status === 'done' || st.status === 'stopped'
  const elapsedSec = Math.round(((st.finishedAt ?? Date.now()) - scan.startedAt) / 1000)
  const score = finished ? scanScore(scan) : null
  return {
    scan_id: scan.scan_id,
    domain_id: scan.domain_id,
    status: st.status,
    stage: { name: st.stageName, done: st.done, total: st.total },
    budget: {
      requests_used: Math.min(300, Math.round((Math.min(elapsedSec, TOTAL_MS / 1000) / (TOTAL_MS / 1000)) * 214)),
      requests_limit: 300,
      tool_calls_used: ['agent', 'scoring', 'reporting', 'done'].includes(st.status) ? 7 : 0,
      tool_calls_limit: 20,
      elapsed_sec: elapsedSec,
      time_limit_sec: 300,
    },
    started_at: kst(scan.startedAt),
    finished_at: st.finishedAt === null ? null : kst(st.finishedAt),
    safety_score: score?.safety ?? null,
    grade: score?.grade ?? null,
    error_message: null,
  }
}

function todayTasks(scan: MockScan) {
  return pickTodayTasks(scoredFindings(scan)).map(({ finding, safetyAfter }, i) => ({
    rank: i + 1,
    finding_id: finding.id,
    check_id: finding.seed.check_id,
    title: finding.seed.guide.title,
    asset_alias: aliasOf(finding.seed.asset_id),
    risk_score: Math.round(finding.risk),
    severity: severityOf(finding.risk),
    fix_minutes: finding.fixMinutes,
    safety_score_after: safetyAfter,
    grade_after: gradeOf(safetyAfter),
  }))
}

function changedFinding(id: string): ChangedFinding {
  const seed = seedOf(id)
  return {
    finding_id: id,
    check_id: seed.check_id,
    asset_alias: aliasOf(seed.asset_id),
    risk_score: Math.round(riskRaw(factorsOf(seed))),
  }
}

// ---------------------------------------------------------------------------
// 응답 도우미
// ---------------------------------------------------------------------------

const ok = (data?: unknown, status = 200): MockResponse => ({ status, data })
const fail = (status: number, code: string, message: string): MockResponse => ({
  status,
  data: { error: { code, message } },
})
const notFound = () => fail(404, 'NOT_FOUND', '요청한 대상을 찾지 못했습니다.')
const notFinished = () => fail(409, 'SCAN_NOT_FINISHED', '점검이 끝나면 볼 수 있습니다.')

// ---------------------------------------------------------------------------
// 주소별 처리
// ---------------------------------------------------------------------------

type Handler = (params: string[], body: Record<string, unknown>, query: URLSearchParams) => MockResponse
const routes: { method: Method; pattern: RegExp; handler: Handler; public?: boolean }[] = []
const route = (method: Method, pattern: string, handler: Handler, isPublic = false) =>
  routes.push({ method, pattern: new RegExp(`^${pattern}$`), handler, public: isPublic })

// 3장 인증
route('POST', '/auth/login', (_, body) => {
  if (Date.now() < state.lockedUntil) {
    return fail(429, 'TOO_MANY_ATTEMPTS', '로그인을 5회 연속 실패했습니다. 5분 뒤 다시 시도해 주세요.')
  }
  if (body.email !== DEMO_USER.email || body.password !== DEMO_PASSWORD) {
    state.failedLogins += 1
    if (state.failedLogins >= 5) {
      state.lockedUntil = Date.now() + 5 * 60_000
      state.failedLogins = 0
    }
    return fail(401, 'INVALID_CREDENTIALS', '이메일 또는 비밀번호가 맞지 않습니다.')
  }
  state.loggedIn = true
  state.failedLogins = 0
  return ok({ user: DEMO_USER, expires_at: kst(Date.now() + 8 * 3600_000) })
}, true)

route('POST', '/auth/logout', () => {
  state.loggedIn = false
  return ok(undefined, 204)
}, true)

route('GET', '/auth/me', () => ok({ user: DEMO_USER, expires_at: kst(Date.now() + 2 * 3600_000) }))

// 4장 공통·도메인
route('GET', '/health', () => ok({ status: 'ok', llm: 'up', time: kst(Date.now()) }), true)
route('GET', '/checks', () => ok({ items: CHECKS }))

route('POST', '/domains', (_, body) => {
  const name = String(body.domain ?? '').trim().toLowerCase()
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(name)) {
    return fail(400, 'VALIDATION_ERROR', '도메인 형식이 맞지 않습니다. 예: jobnest.test')
  }
  const existing = [...state.domains.values()].find((d) => d.domain === name)
  if (existing) return ok(existing)
  const id = `DOM-${state.domains.size + 1}`
  const domain: Domain = {
    domain_id: id,
    domain: name,
    verify_status: 'pending',
    txt_record: { name: `_a2d-verify.${name}`, value: `a2d-verify=${Math.random().toString(16).slice(2, 18)}` },
    verified_at: null,
    created_at: kst(Date.now()),
  }
  state.domains.set(id, domain)
  return ok(domain, 201)
})

// 내 도메인 목록 (백엔드 PR #14에서 추가). 로그인 뒤 등록·대시보드 중 어디로 갈지 정할 때 쓴다.
route('GET', '/domains', () => ok({ items: [...state.domains.values()] }))

route('GET', '/domains/([^/]+)', ([id]) => {
  const domain = state.domains.get(id)
  return domain ? ok(domain) : notFound()
})

route('POST', '/domains/([^/]+)/verify', ([id]) => {
  const domain = state.domains.get(id)
  if (!domain) return notFound()
  domain.verify_status = 'verified'
  domain.verified_at = kst(Date.now())
  return ok({ domain_id: id, verify_status: 'verified', verified_at: domain.verified_at, reason: null })
})

// 5장 점검
route('POST', '/domains/([^/]+)/scans', ([id]) => {
  const domain = state.domains.get(id)
  if (!domain) return notFound()
  if (domain.verify_status !== 'verified') {
    return fail(409, 'DOMAIN_NOT_VERIFIED', '도메인 소유권이 확인되지 않아 점검을 시작할 수 없습니다.')
  }
  if (runningScan(id)) return fail(409, 'SCAN_IN_PROGRESS', '이미 진행 중인 점검이 있습니다.')

  const previous = latestFinishedScan(id)
  // 담당자가 직전 "오늘 할 일" 1번을 고쳤다고 본다.
  const fixed = previous ? todayTasks(previous)[0]?.finding_id : undefined
  let open = previous
    ? previous.openFindingIds.filter((f) => f !== fixed)
    : id === 'DOM-1'
      ? FINDINGS.map((f) => f.finding_id)
      : []
  // 감시 시연: 모두 고친 뒤(100점) 다음 재점검에서 새 테스트 서버가 열린 것으로 본다.
  const testServerOpen =
    id === 'DOM-1' && !!previous && (previous.testServerOpen || previous.openFindingIds.length === 0)
  if (testServerOpen && !previous?.testServerOpen) open = [...open, TEST_FINDING.finding_id]
  const scan: MockScan = {
    scan_id: `S-${String(state.scans.length + 1).padStart(4, '0')}`,
    domain_id: id,
    startedAt: Date.now(),
    stoppedAt: null,
    openFindingIds: open,
    previous_scan_id: previous?.scan_id ?? null,
    testServerOpen,
  }
  state.scans.push(scan)
  return ok({ scan_id: scan.scan_id, status: 'queued', previous_scan_id: scan.previous_scan_id }, 202)
})

route('GET', '/scans/([^/]+)', ([id]) => {
  const scan = findScan(id)
  return scan ? ok(scanResponse(scan)) : notFound()
})

route('POST', '/scans/([^/]+)/stop', ([id]) => {
  const scan = findScan(id)
  if (!scan) return notFound()
  if (!isFinished(scan)) scan.stoppedAt = Date.now()
  return ok(scanResponse(scan))
})

// 6장 대시보드
route('GET', '/domains/([^/]+)/summary', ([id]) => {
  const domain = state.domains.get(id)
  if (!domain) return notFound()
  const latest = latestFinishedScan(id)
  const running = runningScan(id)
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  if (!latest) {
    const empty: Summary = {
      domain_id: id, domain: domain.domain, latest_scan: null, running_scan_id: running?.scan_id ?? null,
      safety_score: 100, grade: 'A', org_risk_score: 0, score_formula: '', counts, asset_count: 0,
      today_tasks: [], alerts: [],
    }
    return ok(empty)
  }
  const scored = scoredFindings(latest)
  scored.forEach((f) => (counts[severityOf(f.risk)] += 1))
  const score = scanScore(latest)
  const sorted = scored.map((f) => Math.round(f.risk)).sort((a, b) => b - a)
  const formula = sorted.length
    ? `0.7 × ${sorted[0]} + 0.3 × (${sorted.slice(1, 6).join(' + ') || 0}) ÷ 5 = ${score.orgRisk}`
    : '발견 없음'
  // 직전 점검에 없던 자산·발견을 알린다(FR-15).
  const prev = latest.previous_scan_id ? findScan(latest.previous_scan_id) : undefined
  const alerts: Alert[] = []
  if (prev) {
    if (latest.testServerOpen && !prev.testServerOpen) {
      alerts.push({ type: 'new_asset', message: `새 하위 도메인 ${TEST_ASSET.host}이 발견됐습니다.`, asset_id: TEST_ASSET.asset_id, finding_id: null })
    }
    for (const fid of latest.openFindingIds.filter((f) => !prev.openFindingIds.includes(f))) {
      const seed = seedOf(fid)
      alerts.push({ type: 'new_finding', message: `${aliasOf(seed.asset_id)}에서 새 발견: ${checkName(seed.check_id)}`, asset_id: seed.asset_id, finding_id: fid })
    }
  }
  const summary: Summary = {
    domain_id: id,
    domain: domain.domain,
    latest_scan: { scan_id: latest.scan_id, finished_at: kst(scanStatus(latest).finishedAt!), status: scanStatus(latest).status },
    running_scan_id: running?.scan_id ?? null,
    safety_score: score.safety,
    grade: score.grade,
    org_risk_score: score.orgRisk,
    score_formula: formula,
    counts,
    asset_count: id === 'DOM-1' ? assetsOf(latest).length : 0,
    today_tasks: todayTasks(latest),
    alerts,
  }
  return ok(summary)
})

route('GET', '/scans/([^/]+)/assets', ([id]) => {
  const scan = findScan(id)
  if (!scan) return notFound()
  if (scan.domain_id !== 'DOM-1') return ok({ items: [] })
  const scored = scoredFindings(scan)
  const items: Asset[] = assetsOf(scan).map((a) => {
    const mine = scored.filter((f) => f.seed.asset_id === a.asset_id)
    const top = mine.reduce((max, f) => Math.max(max, f.risk), -1)
    return {
      ...a,
      importance: importanceOf(a.asset_id),
      is_new: a.asset_id === TEST_ASSET.asset_id && !(scan.previous_scan_id && findScan(scan.previous_scan_id)?.testServerOpen),
      finding_count: mine.length,
      max_severity: mine.length ? severityOf(top) : null,
    }
  })
  return ok({ items })
})

route('PATCH', '/domains/([^/]+)/assets/([^/]+)', ([domainId, assetId], body) => {
  const value = Number(body.importance)
  if (!Number.isInteger(value) || value < 1 || value > 5) {
    return fail(400, 'VALIDATION_ERROR', '자산 중요도는 1~5 사이 정수여야 합니다.')
  }
  if (!ALL_ASSETS.some((a) => a.asset_id === assetId)) return notFound()
  state.importanceOverride.set(assetId, value)
  const latest = latestFinishedScan(domainId)
  const score = latest ? scanScore(latest) : { safety: 100, grade: 'A' as Grade }
  return ok({
    asset: { asset_id: assetId, importance: importanceOf(assetId) },
    summary: { safety_score: score.safety, grade: score.grade },
  })
})

// 7장 발견
route('GET', '/scans/([^/]+)/findings', ([id], _, q) => {
  const scan = findScan(id)
  if (!scan) return notFound()
  const severities = q.get('severity')?.split(',')
  const items = scan.openFindingIds
    .map((f) => findingSummary(scan, f))
    .filter((f) => !q.get('asset_id') || f.asset_id === q.get('asset_id'))
    .filter((f) => !severities || severities.includes(f.severity))
    .filter((f) => !q.get('status') || f.status === q.get('status'))
    .filter((f) => !q.get('check_id') || f.check_id === Number(q.get('check_id')))
    .sort((a, b) => b.risk_score - a.risk_score)
  return ok({ items })
})

route('GET', '/findings/([^/]+)', ([id]) => {
  const seed = ALL_FINDINGS.find((f) => f.finding_id === id)
  if (!seed) return notFound()
  const scan = [...state.scans].reverse().find((s) => s.openFindingIds.includes(id)) ?? state.scans[0]
  const factors = factorsOf(seed)
  const summary = findingSummary(scan, id)
  // 상세 응답에는 first_seen_scan_id와 최상위 risk_score가 없다(명세 7장).
  const { first_seen_scan_id: _firstSeen, risk_score: _risk, ...rest } = summary
  const detail: FindingDetail = {
    ...rest,
    scan_id: scan.scan_id,
    location: seed.location,
    score: {
      exposure: factors.e,
      exploitability: factors.x,
      data_sensitivity: factors.d,
      asset_importance: factors.c,
      asset_importance_fixed: FIXED_IMPORTANCE_CHECKS.has(seed.check_id),
      confidence_factor: confidenceFactor(seed.confidence),
      risk_score: summary.risk_score,
      formula: riskFormula(factors),
    },
    evidence: seed.evidence,
    cves: [],
    detected_at: kst(scan.startedAt + 4000),
  }
  return ok(detail)
})

// 8장 조치 가이드
route('GET', '/scans/([^/]+)/report', ([id]) => {
  const scan = findScan(id)
  if (!scan) return notFound()
  if (!isFinished(scan)) return notFinished()
  const tasks = todayTasks(scan)
  const guide: Guide = {
    scan_id: id,
    source: 'llm',
    verification: { passed: tasks.length, total: tasks.length },
    generated_at: kst(scanStatus(scan).finishedAt!),
    items: tasks.map((t) => {
      const seed = seedOf(t.finding_id)
      return {
        rank: t.rank,
        finding_ids: [t.finding_id],
        ...seed.guide,
        fix_minutes: t.fix_minutes,
        safety_score_after: t.safety_score_after,
        verified: true,
      }
    }),
  }
  return ok(guide)
})

route('POST', '/scans/([^/]+)/questions', ([id], body) => {
  const scan = findScan(id)
  if (!scan) return notFound()
  const question = String(body.question ?? '')
  if (!question.trim() || question.length > 500) {
    return fail(400, 'VALIDATION_ERROR', '질문은 1~500자로 적어 주세요.')
  }
  const keywords: [RegExp, string][] = [
    [/백업|backup|db\.sql|파일/i, 'F-0007'],
    [/api|지원자|개인정보|이메일|전화/i, 'F-0012'],
    [/관리자|admin|로그인/i, 'F-0015'],
  ]
  const hit = keywords.find(([re, fid]) => re.test(question) && scan.openFindingIds.includes(fid))
  if (!hit) {
    return ok({ answer: '이번 점검 결과로는 답할 근거가 없습니다.', finding_ids: [], verification: { passed: true } })
  }
  const seed = seedOf(hit[1])
  return ok({
    answer: `${seed.guide.why_risky} ${seed.guide.expected_damage}`,
    finding_ids: [hit[1]],
    verification: { passed: true },
  })
})

// 9장 기록
route('GET', '/domains/([^/]+)/history', ([id]) => {
  const scans = state.scans.filter((s) => s.domain_id === id && isFinished(s))
  const items = scans.map((scan) => {
    const prev = scan.previous_scan_id ? findScan(scan.previous_scan_id) : undefined
    const score = scanScore(scan)
    return {
      scan_id: scan.scan_id,
      finished_at: kst(scanStatus(scan).finishedAt!),
      status: scanStatus(scan).status,
      safety_score: score.safety,
      grade: score.grade,
      new_count: scan.openFindingIds.filter((f) => !prev?.openFindingIds.includes(f)).length,
      resolved_count: prev ? prev.openFindingIds.filter((f) => !scan.openFindingIds.includes(f)).length : 0,
    }
  })
  return ok({ items })
})

route('GET', '/scans/([^/]+)/changes', ([id]) => {
  const scan = findScan(id)
  if (!scan) return notFound()
  if (!isFinished(scan)) return notFinished()
  const prev = scan.previous_scan_id ? findScan(scan.previous_scan_id) : undefined
  const after = scanScore(scan)
  const before = prev ? scanScore(prev) : null
  return ok({
    scan_id: id,
    previous_scan_id: prev?.scan_id ?? null,
    safety_score: { before: before?.safety ?? null, after: after.safety },
    grade: { before: before?.grade ?? null, after: after.grade },
    resolved_findings: prev ? prev.openFindingIds.filter((f) => !scan.openFindingIds.includes(f)).map(changedFinding) : [],
    new_findings: scan.openFindingIds.filter((f) => !prev?.openFindingIds.includes(f)).map(changedFinding),
    new_assets:
      scan.testServerOpen && !prev?.testServerOpen && prev
        ? [{ asset_id: TEST_ASSET.asset_id, alias: TEST_ASSET.alias, host: TEST_ASSET.host }]
        : [],
    removed_assets: [],
  })
})

route('GET', '/scans/([^/]+)/audit', ([id], _, q) => {
  const scan = findScan(id)
  if (!scan) return notFound()
  const t = (sec: number) => kst(scan.startedAt + sec * 1000)
  const entries: AuditEntry[] = [
    { at: t(1), actor: 'system', tool: 'discover_assets', args: { domain_id: scan.domain_id }, result_summary: `자산 ${assetsOf(scan).length}개`, rejected: false, reject_reason: null },
    { at: t(3), actor: 'system', tool: 'check_paths', args: { asset_id: 'A-001', category: 'backup' }, result_summary: scan.openFindingIds.includes('F-0007') ? '발견 F-0007 기록' : '이상 없음', rejected: false, reject_reason: null },
    { at: t(4), actor: 'system', tool: 'check_paths', args: { asset_id: 'A-003', category: 'admin' }, result_summary: scan.openFindingIds.includes('F-0015') ? '발견 F-0015 기록' : '이상 없음', rejected: false, reject_reason: null },
    { at: t(6), actor: 'attack', tool: 'check_unauth_api', args: { asset_id: 'A-002', endpoint_id: 'E-004' }, result_summary: scan.openFindingIds.includes('F-0012') ? '발견 F-0012 기록' : '이상 없음', rejected: false, reject_reason: null },
    { at: t(7), actor: 'attack', tool: 'check_paths', args: { asset_id: 'A-099', category: 'backup' }, result_summary: null, rejected: true, reject_reason: '소유권이 확인된 자산이 아님' },
    { at: t(9), actor: 'defense', tool: 'submit_report', args: { items: 3 }, result_summary: '근거 검증 통과', rejected: false, reject_reason: null },
  ]
  const items = entries
    .filter((e) => !q.get('actor') || e.actor === q.get('actor'))
    .filter((e) => q.get('rejected') !== 'true' || e.rejected)
  return ok({ items })
})

// ---------------------------------------------------------------------------
// 진입점
// ---------------------------------------------------------------------------

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export async function handleMock(method: Method, fullPath: string, body?: unknown): Promise<MockResponse> {
  // 실제 네트워크처럼 조금 기다린다. 로딩 화면을 만들 때 필요하다.
  await delay(180 + Math.random() * 220)

  const url = new URL(fullPath, 'http://mock')
  // 규칙은 주소 전체가 맞아야(^…$) 걸리므로 순서와 상관없이 하나만 맞는다.
  for (const r of routes) {
    if (r.method !== method) continue
    const match = url.pathname.match(r.pattern)
    if (!match) continue
    if (!r.public && !state.loggedIn) {
      return fail(401, 'UNAUTHENTICATED', '다시 로그인해 주세요.')
    }
    return r.handler(match.slice(1), (body ?? {}) as Record<string, unknown>, url.searchParams)
  }
  return notFound()
}
