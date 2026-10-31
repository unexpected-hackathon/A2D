// API 응답 모양. docs/A2D_API명세.md를 그대로 옮겼다. 명세가 바뀌면 여기부터 고친다.

// ---- 코드 값 (명세 1장) ----
export type Grade = 'A' | 'B' | 'C' | 'D' | 'F'
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type Confidence = 'confirmed' | 'likely' | 'needs_review'
export type FindingStatus = 'open' | 'new' | 'resolved'
export type VerifyStatus = 'pending' | 'verified' | 'failed'
export type ScanStatus =
  | 'queued'
  | 'discovering'
  | 'checking'
  | 'agent'
  | 'scoring'
  | 'reporting'
  | 'done'
  | 'stopped'
  | 'failed'
export type ReportSource = 'llm' | 'template'

// ---- 인증 (3장) ----
export interface User {
  user_id: string
  email: string
  name: string
}
export interface SessionInfo {
  user: User
  expires_at: string
}

// ---- 공통·도메인 (4장) ----
export interface Health {
  status: 'ok'
  llm: 'up' | 'down'
  time: string
}
export interface Check {
  check_id: number
  name: string
  category: string
  category_name: string
  phase: '1차' | '1차·식별' | '2차'
  scored: boolean
}
export interface Domain {
  domain_id: string
  domain: string
  verify_status: VerifyStatus
  txt_record: { name: string; value: string }
  verified_at: string | null
  created_at: string
}
export interface VerifyResult {
  domain_id: string
  verify_status: VerifyStatus
  verified_at: string | null
  reason: string | null
}

// ---- 점검 (5장) ----
// 추가 점검(Attack 에이전트, FR-04)의 상태. message는 서버가 정한 화면 문장이다.
export type AttackStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed' | 'stopped'
export interface AttackState {
  status: AttackStatus
  reason: string | null
  message: string | null
}
export interface ScanStarted {
  scan_id: string
  status: ScanStatus
  previous_scan_id: string | null
}
export interface Scan {
  scan_id: string
  domain_id: string
  status: ScanStatus
  stage: { name: string; done: number; total: number }
  budget: {
    requests_used: number
    requests_limit: number
    tool_calls_used: number
    tool_calls_limit: number
    elapsed_sec: number
    time_limit_sec: number
  }
  started_at: string
  finished_at: string | null
  safety_score: number | null
  grade: Grade | null
  error_message: string | null
  // 이 필드가 생기기 전의 점검·백엔드는 null이거나 없다
  attack?: AttackState | null
}

// ---- 대시보드 (6장) ----
export interface TodayTask {
  rank: number
  finding_id: string
  check_id: number
  title: string
  asset_alias: string
  risk_score: number
  severity: Severity
  fix_minutes: number
  safety_score_after: number
  grade_after: Grade
}
export interface Alert {
  type: 'new_asset' | 'new_finding'
  message: string
  asset_id: string | null
  finding_id: string | null
}
export interface Summary {
  domain_id: string
  domain: string
  latest_scan: { scan_id: string; finished_at: string; status: ScanStatus; attack?: AttackState | null } | null
  running_scan_id: string | null
  safety_score: number
  grade: Grade
  org_risk_score: number
  score_formula: string
  counts: Record<Severity, number>
  asset_count: number
  today_tasks: TodayTask[]
  alerts: Alert[]
}
export interface Asset {
  asset_id: string
  alias: string
  host: string
  url: string
  found_by: number[]
  tags: string[]
  importance: { value: number; source: 'auto' | 'manual'; rule: string | null }
  components: { name: string; version: string; eol: boolean }[]
  tls_version: string | null
  is_new: boolean
  finding_count: number
  max_severity: Severity | null
}

// ---- 발견 (7장) ----
export interface FindingSummary {
  finding_id: string
  check_id: number
  check_name: string
  asset_id: string
  asset_alias: string
  situation: string
  risk_score: number
  severity: Severity
  confidence: Confidence
  status: FindingStatus
  first_seen_scan_id: string
}
// 상세에는 최상위 risk_score가 없고 score.risk_score에만 있다(명세 7장).
export interface FindingDetail extends Omit<FindingSummary, 'first_seen_scan_id' | 'risk_score'> {
  scan_id: string
  location: string
  score: {
    exposure: number
    exploitability: number
    data_sensitivity: number
    asset_importance: number
    asset_importance_fixed: boolean
    confidence_factor: number
    risk_score: number
    formula: string | null // 참고 정보(info)는 산식이 없다
  }
  evidence: string
  cves: { id: string; cvss: number; kev: boolean }[]
  detected_at: string
}

// ---- 조치 가이드 (8장) ----
export interface GuideItem {
  rank: number
  finding_ids: string[]
  title: string
  why_risky: string
  expected_damage: string
  fix_steps: string[]
  fix_minutes: number
  safety_score_after: number
  verified: boolean
}
export interface Guide {
  scan_id: string
  source: ReportSource
  verification: { passed: number; total: number }
  generated_at: string
  items: GuideItem[]
}
export interface Answer {
  answer: string
  finding_ids: string[]
  verification: { passed: boolean }
}

// ---- 기록 (9장) ----
export interface HistoryItem {
  scan_id: string
  finished_at: string
  status: ScanStatus
  safety_score: number
  grade: Grade
  new_count: number
  resolved_count: number
}
export interface ChangedFinding {
  finding_id: string
  check_id: number
  asset_alias: string
  risk_score: number
}
export interface Changes {
  scan_id: string
  previous_scan_id: string | null
  safety_score: { before: number | null; after: number }
  grade: { before: Grade | null; after: Grade }
  resolved_findings: ChangedFinding[]
  new_findings: ChangedFinding[]
  new_assets: { asset_id: string; alias: string; host: string }[]
  removed_assets: { asset_id: string; alias: string; host: string }[]
}
export interface AuditEntry {
  at: string
  actor: 'system' | 'attack' | 'defense'
  tool: string
  args: Record<string, unknown>
  result_summary: string | null
  rejected: boolean
  reject_reason: string | null
}

// 목록 응답은 모두 { items: [...] } 모양이다.
export interface ItemList<T> {
  items: T[]
}
