// 가짜 응답의 재료. target/의 기본 시연 프로필(#16 · #8 · #18)과 같은 내용이다.
// 모든 값은 예시다. 개인정보처럼 보이는 값은 가려진 형태로만 둔다.

import type { Asset, Check, Confidence } from '../types'

export const DEMO_DOMAIN = 'jobnest.test'

export const DEMO_USER = {
  user_id: 'U-1',
  email: 'admin@jobnest.test',
  name: 'JobNest IT 담당자',
}
export const DEMO_PASSWORD = 'a2d-demo'

// docs/A2D_점검점수설계.md 1장의 34개 항목
const CHECK_ROWS: [number, string, string, Check['phase'], boolean][] = [
  [1, '하위 도메인 찾기', 'A', '1차', false],
  [2, '홈페이지 링크 수집', 'A', '1차', false],
  [3, 'robots.txt · 사이트맵', 'A', '1차', false],
  [4, '위탁 서비스 연결', 'A', '1차', false],
  [5, '인증서 발급 기록 조회', 'A', '1차', false],
  [6, '하위 도메인 탈취 가능성', 'A', '1차', true],
  [7, '열린 포트 확인', 'A', '2차', false],
  [8, '백업·DB 덤프 파일', 'B', '1차', true],
  [9, '설정 파일 · 소스 저장소', 'B', '1차', true],
  [10, '파일 목록 공개', 'B', '1차', true],
  [11, '오류 메시지 정보 노출', 'B', '1차', true],
  [12, '화면 코드 속 비밀키', 'B', '1차', true],
  [13, '소스맵 공개', 'B', '1차', true],
  [14, '클라우드 저장소 공개', 'B', '1차', true],
  [15, '유출 계정 조회', 'B', '2차', false],
  [16, '인증 없는 API', 'C', '1차', true],
  [17, 'API 설명서 공개', 'C', '1차', true],
  [18, '관리자 페이지 노출', 'C', '1차', true],
  [19, '개발·테스트 서버 노출', 'C', '1차', true],
  [20, '운영·상태 확인 페이지', 'C', '1차', true],
  [21, 'CORS 과다 허용', 'C', '1차', true],
  [22, '보안 신고 창구 안내', 'C', '2차', false],
  [23, '서버 버전 표시 + 알려진 취약점', 'D', '1차', true],
  [24, '홈페이지 컴포넌트 버전', 'D', '1차·식별', false],
  [25, '지원 종료 버전', 'D', '1차', true],
  [26, 'HTTPS 미사용', 'E', '1차', true],
  [27, 'HTTP → HTTPS 자동 전환', 'E', '1차', true],
  [28, '인증서 만료·오류', 'E', '1차', true],
  [29, '오래된 암호화 방식', 'E', '2차', false],
  [30, '보안 헤더 누락', 'E', '1차', true],
  [31, '쿠키 보안 설정', 'E', '1차', true],
  [32, '메일 사칭 방지 (SPF·DMARC)', 'F', '1차', true],
  [33, '도메인 만료일', 'F', '1차', true],
  [34, 'BaaS 공개 접근', 'C', '1차', true],
]

const CATEGORY_NAME: Record<string, string> = {
  A: '자산 찾기',
  B: '노출된 파일·정보',
  C: '접근 통제',
  D: '소프트웨어 버전',
  E: '전송·브라우저 설정',
  F: '메일·도메인',
}

export const CHECKS: Check[] = CHECK_ROWS.map(([check_id, name, category, phase, scored]) => ({
  check_id,
  name,
  category,
  category_name: CATEGORY_NAME[category],
  phase,
  scored,
}))

export const checkName = (id: number) => CHECKS.find((c) => c.check_id === id)?.name ?? `#${id}`

// 자산. finding_count와 max_severity는 점검마다 server.ts가 채운다.
type AssetSeed = Omit<Asset, 'finding_count' | 'max_severity' | 'is_new'>
const d = DEMO_DOMAIN
export const ASSETS: AssetSeed[] = [
  {
    asset_id: 'A-001', alias: 'www', host: `www.${d}`, url: `https://www.${d}`, found_by: [1, 2],
    tags: ['대표', 'login'], importance: { value: 4, source: 'auto', rule: '대표 도메인' },
    components: [{ name: 'nginx', version: '1.27.4', eol: false }, { name: 'jQuery', version: '3.4.1', eol: false }],
    tls_version: 'TLS 1.3',
  },
  {
    asset_id: 'A-002', alias: 'api', host: `api.${d}`, url: `https://api.${d}`, found_by: [1, 2],
    tags: ['api', '개인정보'], importance: { value: 5, source: 'auto', rule: '개인정보 형태 응답' },
    components: [{ name: 'FastAPI', version: '0.115', eol: false }],
    tls_version: 'TLS 1.3',
  },
  {
    asset_id: 'A-003', alias: 'admin', host: `admin.${d}`, url: `https://admin.${d}`, found_by: [1],
    tags: ['관리자'], importance: { value: 4, source: 'auto', rule: '관리자 경로' },
    components: [], tls_version: 'TLS 1.3',
  },
  {
    asset_id: 'A-004', alias: 'staging', host: `staging.${d}`, url: `https://staging.${d}`, found_by: [1, 5],
    tags: ['테스트'], importance: { value: 3, source: 'auto', rule: 'staging·dev·test 이름' },
    components: [{ name: 'Next.js', version: '14.1.0', eol: false }], tls_version: 'TLS 1.3',
  },
  {
    asset_id: 'A-005', alias: 'dev', host: `dev.${d}`, url: `https://dev.${d}`, found_by: [1],
    tags: ['테스트'], importance: { value: 3, source: 'auto', rule: 'staging·dev·test 이름' },
    components: [], tls_version: 'TLS 1.3',
  },
  {
    asset_id: 'A-006', alias: 'recruit', host: `recruit.${d}`, url: `https://recruit.${d}`, found_by: [4],
    tags: ['위탁 서비스'], importance: { value: 3, source: 'auto', rule: '위탁 서비스 연결' },
    components: [], tls_version: 'TLS 1.2',
  },
  {
    asset_id: 'A-007', alias: 'promo', host: `promo.${d}`, url: `https://promo.${d}`, found_by: [1, 4],
    tags: ['홍보'], importance: { value: 2, source: 'auto', rule: '홍보용 정적 페이지' },
    components: [], tls_version: 'TLS 1.3',
  },
]

// 감시 시연용: 모든 문제를 고친 뒤 재점검하면 새로 열리는 테스트 서버 (target의 test-server on)
export const TEST_ASSET: AssetSeed = {
  asset_id: 'A-008', alias: 'test', host: `test.${d}`, url: `https://test.${d}`, found_by: [1, 5],
  tags: ['테스트'], importance: { value: 3, source: 'auto', rule: 'staging·dev·test 이름' },
  components: [{ name: 'Next.js', version: '13.4.0', eol: true }], tls_version: 'TLS 1.3',
}

// 시연 결함 3개 (target 기본 프로필). c는 자산 중요도에서 가져온다.
export interface FindingSeed {
  finding_id: string
  check_id: number
  asset_id: string
  situation: string
  location: string
  e: number
  x: number
  d: number
  confidence: Confidence
  evidence: string
  fix_minutes: number
  guide: { title: string; why_risky: string; expected_damage: string; fix_steps: string[] }
}

export const FINDINGS: FindingSeed[] = [
  {
    finding_id: 'F-0012',
    check_id: 16,
    asset_id: 'A-002',
    situation: '개인정보 형태 데이터 반환',
    location: `GET https://api.${d}/api/v1/applicants/1024`,
    e: 5, x: 5, d: 5,
    confidence: 'confirmed',
    evidence: '200 응답, 이메일 형식 3건(j***@***.com 등)과 전화번호 형식 3건 포함',
    fix_minutes: 60,
    guide: {
      title: '지원자 정보가 로그인 없이 보입니다',
      why_risky: '지원자 조회 주소를 아는 사람은 누구나 다른 지원자의 이메일과 전화번호를 볼 수 있습니다.',
      expected_damage: '번호만 바꿔 가며 전체 지원자 정보를 모을 수 있어 대량 유출로 이어질 수 있습니다.',
      fix_steps: [
        '지원자 조회 API에 로그인 확인을 추가합니다.',
        '응답에서 화면에 필요 없는 전화번호를 뺍니다.',
      ],
    },
  },
  {
    finding_id: 'F-0007',
    check_id: 8,
    asset_id: 'A-001',
    situation: '파일 형식까지 확인',
    location: `GET https://www.${d}/backup.zip`,
    e: 5, x: 5, d: 5,
    confidence: 'confirmed',
    evidence: '200 응답, ZIP 서명(PK) 확인, 파일 크기 18MB. 내용은 내려받지 않음',
    fix_minutes: 10,
    guide: {
      title: '누구나 내려받을 수 있는 지원자 백업 파일',
      why_risky: 'www 서버의 backup.zip과 db.sql은 주소만 알면 누구나 내려받을 수 있습니다.',
      expected_damage: '지원자 이력서와 연락처가 한 번에 통째로 유출될 수 있습니다.',
      fix_steps: [
        '웹 공개 폴더에서 backup.zip과 db.sql을 지웁니다.',
        '백업은 웹 서버 밖의 비공개 저장소에 둡니다.',
      ],
    },
  },
  {
    finding_id: 'F-0015',
    check_id: 18,
    asset_id: 'A-003',
    situation: '로그인 화면 보임',
    location: `GET https://admin.${d}/`,
    e: 5, x: 3, d: 4,
    confidence: 'confirmed',
    evidence: '200 응답, "채용 담당자 콘솔" 로그인 양식. 로그인은 시도하지 않음',
    fix_minutes: 30,
    guide: {
      title: '외부에서 열리는 채용 관리자 화면',
      why_risky: '관리자 로그인 화면이 인터넷 어디서나 열려 무차별 대입 공격의 표적이 됩니다.',
      expected_damage: '관리자 계정이 뚫리면 공고와 지원자 정보를 모두 볼 수 있습니다.',
      fix_steps: [
        '관리자 화면을 회사 IP나 VPN에서만 열리게 제한합니다.',
        '관리자 계정에 2단계 인증을 켭니다.',
      ],
    },
  },
]

// 감시 시연용 새 발견: 테스트 서버에 디버그 표시가 켜진 채 외부에 열림
export const TEST_FINDING: FindingSeed = {
  finding_id: 'F-0020',
  check_id: 19,
  asset_id: 'A-008',
  situation: '디버그 표시 있음',
  location: `GET https://test.${d}/`,
  e: 5, x: 4, d: 3,
  confidence: 'confirmed',
  evidence: '200 응답, "DEBUG=True · 운영 지원자 DB 복제본 사용 중" 표시',
  fix_minutes: 15,
  guide: {
    title: '새로 열린 테스트 서버가 외부에 보입니다',
    why_risky: '디버그 표시가 켜진 테스트 서버가 인터넷에 열려 내부 구조와 오류 내용이 그대로 보입니다.',
    expected_damage: '운영 데이터 복제본을 쓰고 있어 지원자 정보가 새어 나갈 수 있습니다.',
    fix_steps: ['테스트 서버를 외부에서 닫거나 회사 IP에서만 열리게 합니다.', '디버그 표시를 끕니다.'],
  },
}
