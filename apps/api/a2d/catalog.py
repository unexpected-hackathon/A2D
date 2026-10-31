"""점검 항목 34개와 항목별 점수 기본값(docs/A2D_점검점수설계.md 1장·2.3).

- CHECKS: GET /checks가 내려주는 목록
- SITUATIONS: 발견의 "상황"별 E·X·D·C(고정)·신뢰도. 점수는 scoring.py가 계산한다
- FIX_MINUTES: 항목별 표준 조치 시간(분). PRD 미결 사항이라 팀 검토 전 초기값이다
- GUIDES: LLM이 없을 때 쓰는 기본 가이드 문장(FR-11)이자 Defense 에이전트의 조치 문안 범위
"""

from __future__ import annotations

from dataclasses import dataclass

CATEGORIES = {
    "A": "자산 찾기",
    "B": "노출된 파일·정보",
    "C": "접근 통제",
    "D": "소프트웨어 버전",
    "E": "전송·브라우저 설정",
    "F": "메일·도메인",
}

# (번호, 이름, 분류, 구분)
_CHECKS = [
    (1, "하위 도메인 찾기", "A", "1차"),
    (2, "홈페이지 링크 수집", "A", "1차"),
    (3, "robots.txt · 사이트맵", "A", "1차"),
    (4, "위탁 서비스 연결", "A", "1차"),
    (5, "인증서 발급 기록 조회", "A", "1차"),
    (6, "하위 도메인 탈취 가능성", "A", "1차"),
    (7, "열린 포트 확인", "A", "2차"),
    (8, "백업·DB 덤프 파일", "B", "1차"),
    (9, "설정 파일 · 소스 저장소", "B", "1차"),
    (10, "파일 목록 공개", "B", "1차"),
    (11, "오류 메시지 정보 노출", "B", "1차"),
    (12, "화면 코드 속 비밀키", "B", "1차"),
    (13, "소스맵 공개", "B", "1차"),
    (14, "클라우드 저장소 공개", "B", "1차"),
    (15, "유출 계정 조회", "B", "2차"),
    (16, "인증 없는 API", "C", "1차"),
    (17, "API 설명서 공개", "C", "1차"),
    (18, "관리자 페이지 노출", "C", "1차"),
    (19, "개발·테스트 서버 노출", "C", "1차"),
    (20, "운영·상태 확인 페이지", "C", "1차"),
    (21, "CORS 과다 허용", "C", "1차"),
    (22, "보안 신고 창구 안내", "C", "2차"),
    (23, "서버 버전 표시 + 알려진 약점", "D", "1차"),
    (24, "홈페이지 부품 버전", "D", "1차·식별"),
    (25, "지원 종료 버전", "D", "1차"),
    (26, "HTTPS 미사용", "E", "1차"),
    (27, "HTTP → HTTPS 자동 전환", "E", "1차"),
    (28, "인증서 만료·오류", "E", "1차"),
    (29, "오래된 암호화 방식", "E", "2차"),
    (30, "보안 헤더 누락", "E", "1차"),
    (31, "쿠키 보안 설정", "E", "1차"),
    (32, "메일 사칭 방지 (SPF·DMARC)", "F", "1차"),
    (33, "도메인 만료일", "F", "1차"),
    (34, "백엔드 대행 서비스 공개 접근", "C", "1차"),
]

DISCOVERY_IDS = {1, 2, 3, 4, 5}
UNSCORED_IDS = DISCOVERY_IDS | {24} | {7, 15, 22, 29}


@dataclass(frozen=True)
class Check:
    check_id: int
    name: str
    category: str
    phase: str

    @property
    def scored(self) -> bool:
        return self.check_id not in UNSCORED_IDS

    def to_api(self) -> dict:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "category": self.category,
            "category_name": CATEGORIES[self.category],
            "phase": self.phase,
            "scored": self.scored,
        }


CHECKS: dict[int, Check] = {n: Check(n, name, cat, ph) for n, name, cat, ph in _CHECKS}


def check_name(check_id: int) -> str:
    return CHECKS[check_id].name


@dataclass(frozen=True)
class Situation:
    check_id: int
    key: str
    text: str  # 점검·점수 설계 2.3 "상황" 열
    e: int
    x: int
    d: int
    c_fixed: int | None  # None이면 자산 중요도를 쓴다
    confidence: str  # confirmed | likely | needs_review
    info: bool = False  # 참고 정보(점수 미반영)


# C 고정 항목: #6(4), #12(5), #14(5), #32(5), #33(5), #34(5)
_S = [
    Situation(6, "dangling", "해지된 서비스 안내문 확인", 5, 4, 4, 4, "likely"),
    Situation(8, "confirmed", "파일 형식까지 확인", 5, 5, 5, None, "confirmed"),
    Situation(8, "unknown_format", "응답은 있으나 형식 불명", 5, 5, 5, None, "needs_review"),
    Situation(9, "env", "설정 파일(.env) 공개", 5, 5, 5, None, "confirmed"),
    Situation(9, "git", "소스 저장소(.git) 공개", 5, 5, 4, None, "confirmed"),
    Situation(9, "sftp", "FTP·SFTP 접속 정보 파일 공개", 5, 5, 5, None, "confirmed"),
    Situation(9, "config", "DB 비밀번호가 든 설정 파일·백업 공개", 5, 5, 5, None, "confirmed"),
    Situation(10, "basic", "파일 목록 공개", 5, 5, 3, None, "confirmed"),
    Situation(10, "sensitive", "목록에 민감해 보이는 파일 이름", 5, 5, 5, None, "confirmed"),
    Situation(11, "basic", "내부 코드 기록·경로·DB 오류", 5, 2, 3, None, "confirmed"),
    Situation(12, "secret", "고유 형태 키 발견 (유효 여부는 확인 안 함)", 5, 5, 5, 5, "confirmed"),
    Situation(13, "basic", "소스맵만 열림", 5, 1, 2, None, "confirmed"),
    Situation(14, "listing", "파일 목록 공개", 5, 5, 4, 5, "confirmed"),
    Situation(14, "sensitive", "목록에 민감해 보이는 파일 이름", 5, 5, 5, 5, "confirmed"),
    Situation(16, "pii", "개인정보 형태 데이터 반환", 5, 5, 5, None, "confirmed"),
    Situation(16, "data", "데이터는 오지만 개인정보 아님", 5, 5, 2, None, "confirmed"),
    Situation(17, "basic", "API 설명서 공개", 5, 2, 2, None, "confirmed"),
    Situation(17, "graphql", "GraphQL 스키마 조회 공개", 5, 3, 2, None, "confirmed"),
    Situation(18, "basic", "로그인 화면 보임", 5, 3, 4, None, "confirmed"),
    Situation(19, "basic", "개발·테스트 서버 외부 노출", 5, 2, 3, None, "confirmed"),
    Situation(19, "debug", "디버그 표시 있음", 5, 4, 3, None, "confirmed"),
    Situation(20, "env", "환경 변수·설정 노출", 5, 4, 5, None, "confirmed"),
    Situation(20, "status", "상태·통계만", 5, 4, 3, None, "confirmed"),
    Situation(21, "any_origin", "아무 출처·null 허용 + 로그인 정보 허용", 3, 3, 4, None, "likely"),
    Situation(21, "loose_match", "이름 비교 허술", 3, 2, 4, None, "likely"),
    Situation(21, "wildcard", "* 만 있음", 0, 0, 0, None, "confirmed", info=True),
    Situation(23, "kev", "실제 악용 중(KEV 등재)", 5, 5, 4, None, "likely"),
    Situation(23, "cvss9", "CVSS 9.0 이상", 5, 4, 4, None, "likely"),
    Situation(23, "cvss7", "CVSS 7.0~8.9", 5, 3, 4, None, "likely"),
    Situation(23, "cvss_low", "CVSS 7.0 미만", 5, 2, 4, None, "likely"),
    Situation(25, "server", "서버 쪽 소프트웨어 지원 종료", 5, 2, 3, None, "likely"),
    Situation(26, "basic", "HTTPS 미사용", 2, 3, 3, None, "confirmed"),
    Situation(26, "login", "로그인·개인정보 입력 화면 있음", 2, 3, 4, None, "confirmed"),
    Situation(27, "basic", "HTTPS 자동 전환 없음", 2, 2, 2, None, "confirmed"),
    Situation(28, "expired", "인증서가 이미 만료됨", 5, 5, 2, None, "confirmed"),
    Situation(28, "expiring14", "인증서 14일 이내 만료", 5, 3, 2, None, "confirmed"),
    Situation(28, "expiring30", "인증서 30일 이내 만료", 5, 2, 2, None, "confirmed"),
    Situation(28, "invalid", "인증서 이름 불일치·자체 서명", 2, 3, 3, None, "confirmed"),
    Situation(30, "basic", "보안 헤더 누락", 3, 2, 1, None, "confirmed"),
    Situation(31, "login", "로그인 쿠키 보안 속성 누락", 3, 2, 3, None, "confirmed"),
    Situation(31, "other", "그 외 쿠키 보안 속성 누락", 3, 2, 1, None, "confirmed"),
    Situation(32, "none", "SPF·DMARC 둘 다 없음", 5, 5, 2, 5, "confirmed"),
    Situation(32, "weak_dmarc", "SPF는 있으나 DMARC 없음 또는 p=none", 5, 4, 2, 5, "confirmed"),
    Situation(32, "weak_spf", "DMARC가 사칭을 막지만 SPF 없음·느슨", 5, 1, 1, 5, "confirmed"),
    Situation(33, "expired", "도메인이 이미 만료됨 (유예 기간)", 5, 5, 5, 5, "confirmed"),
    Situation(33, "expiring30", "도메인 30일 이내 만료", 5, 2, 5, 5, "confirmed"),
    Situation(33, "expiring90", "도메인 90일 이내 만료", 5, 1, 5, 5, "confirmed"),
    Situation(34, "pii", "Supabase에서 개인정보 형태 데이터 반환", 5, 5, 5, 5, "confirmed"),
    Situation(34, "data", "데이터는 오지만 개인정보 아님", 5, 5, 2, 5, "confirmed"),
    Situation(34, "firebase", "Firebase 항목 이름만 확인", 5, 5, 4, 5, "likely"),
]

SITUATIONS: dict[tuple[int, str], Situation] = {(s.check_id, s.key): s for s in _S}

# 항목별 표준 조치 시간(분). 오늘 할 일 동점 처리와 화면 표시에 쓴다.
FIX_MINUTES: dict[int, int] = {
    6: 15, 8: 10, 9: 15, 10: 10, 11: 30, 12: 60, 13: 10, 14: 20, 16: 60, 17: 15, 18: 30,
    19: 30, 20: 15, 21: 30, 23: 60, 25: 120, 26: 60, 27: 15, 28: 30, 30: 30, 31: 20,
    32: 30, 33: 10, 34: 60,
}


@dataclass(frozen=True)
class Guide:
    title: str
    why_risky: str
    expected_damage: str
    fix_steps: tuple[str, ...]


# 기본 가이드(템플릿). {asset}은 자산 별칭으로 바꾼다.
GUIDES: dict[int, Guide] = {
    6: Guide(
        "해지된 외부 서비스를 가리키는 하위 도메인",
        "{asset} 주소가 이미 해지된 외부 서비스를 가리키고 있어, 다른 사람이 그 서비스에 가입하면 우리 주소를 차지할 수 있습니다.",
        "우리 회사 주소로 가짜 채용 공고나 피싱 페이지가 열릴 수 있습니다.",
        ("DNS 관리 화면에서 쓰지 않는 CNAME 레코드를 지웁니다.", "계속 쓸 서비스라면 외부 서비스에 다시 연결합니다."),
    ),
    8: Guide(
        "누구나 내려받을 수 있는 백업 파일",
        "{asset} 서버의 공개 경로에 백업·DB 파일이 남아 있어 주소만 알면 누구나 내려받을 수 있습니다.",
        "지원자 이름·연락처·이력서 같은 회원 정보 전체가 한 번에 유출될 수 있습니다.",
        ("웹 공개 폴더에서 백업·DB 파일을 지웁니다.", "백업은 웹 서버 밖의 접근 제한된 저장소에 둡니다.", "파일 안 비밀번호가 있었다면 바꿉니다."),
    ),
    9: Guide(
        "공개된 설정 파일·소스 저장소",
        "{asset} 서버에서 설정 파일이나 소스 저장소 파일이 그대로 열립니다.",
        "DB 비밀번호와 소스 코드가 새어 나가 서버 전체가 넘어갈 수 있습니다.",
        ("웹 공개 폴더에서 .env와 .git 폴더, 설정 백업(.bak)·sftp.json 파일을 지우거나 웹 서버에서 접근을 막습니다.",
         "파일에 있던 비밀번호와 키를 모두 바꿉니다."),
    ),
    10: Guide(
        "폴더 안 파일 목록이 그대로 보임",
        "{asset} 서버의 폴더 주소를 열면 안에 든 파일 목록이 보입니다.",
        "올려 둔 이력서·증빙 파일을 하나씩 내려받을 수 있습니다.",
        ("웹 서버 설정에서 폴더 목록 보기를 끕니다.", "목록에 있던 민감한 파일은 접근 제한된 저장소로 옮깁니다."),
    ),
    11: Guide(
        "오류 화면에 내부 정보가 보임",
        "{asset} 서버에 없는 주소를 열면 오류 화면에 내부 코드 기록과 서버 경로가 나옵니다.",
        "공격자가 서버 구조와 DB 주소를 알아내 다음 공격을 준비할 수 있습니다.",
        ("운영 서버의 디버그 모드를 끕니다.", "오류가 나면 일반 안내 화면만 보이게 합니다."),
    ),
    12: Guide(
        "화면 코드에 들어 있는 비밀키",
        "{asset} 화면 코드(JS 파일)에 외부 서비스 비밀키가 그대로 들어 있습니다.",
        "누구나 이 키로 클라우드나 결제 서비스를 써서 요금 폭탄이나 데이터 유출이 생길 수 있습니다.",
        ("해당 서비스 관리 화면에서 키를 즉시 폐기하고 새로 발급합니다.", "새 키는 서버에만 두고 화면 코드에서 지웁니다."),
    ),
    13: Guide(
        "화면 코드 원본(소스맵)이 공개됨",
        "{asset} 서버에서 압축된 화면 코드의 원본을 복원하는 소스맵 파일이 열립니다.",
        "개발자 주석과 숨은 API 주소가 드러나 공격 표적을 찾기 쉬워집니다.",
        ("운영 배포에서 소스맵(.map) 파일을 빼거나 접근을 막습니다.",),
    ),
    14: Guide(
        "파일 목록이 열린 클라우드 저장소",
        "우리 사이트가 쓰는 클라우드 저장소({asset})의 파일 목록을 누구나 볼 수 있습니다.",
        "이력서·내보내기 파일·DB 백업 같은 고객 파일이 통째로 유출될 수 있습니다.",
        ("저장소의 공개 목록 권한을 끕니다.", "공개가 필요한 파일만 따로 두고 나머지는 비공개로 바꿉니다."),
    ),
    16: Guide(
        "로그인 없이 개인정보가 보이는 API",
        "{asset} 서버의 조회 API를 로그인 없이 부르면 지원자 이메일과 전화번호가 돌아옵니다.",
        "번호만 바꿔 가며 전체 회원 정보를 모을 수 있어 대량 유출로 이어질 수 있습니다.",
        ("조회 API에 로그인 확인을 추가합니다.", "본인 또는 권한 있는 담당자만 볼 수 있게 권한 검사를 넣습니다.", "응답에서 화면에 필요 없는 개인정보를 뺍니다."),
    ),
    17: Guide(
        "누구나 볼 수 있는 API 설명서",
        "{asset} 서버의 API 설명서가 공개돼 있어 어떤 기능이 있는지 누구나 알 수 있습니다.",
        "공격자가 설명서를 보고 약한 API를 골라 공격할 수 있습니다.",
        ("운영 서버에서 API 설명서 주소를 끄거나 사내에서만 열리게 합니다.",
         "GraphQL은 운영 서버에서 스키마 조회(introspection)를 끕니다."),
    ),
    18: Guide(
        "외부에서 열리는 관리자 로그인 화면",
        "{asset}의 관리자 로그인 화면이 인터넷 어디서나 열립니다.",
        "비밀번호 대입 공격으로 관리자 계정이 털리면 지원자 정보 전체가 넘어갈 수 있습니다.",
        ("관리자 화면은 사내 IP나 VPN에서만 열리게 접근을 제한합니다.", "관리자 계정에 2단계 인증을 켭니다."),
    ),
    19: Guide(
        "외부에 열린 개발·테스트 서버",
        "시험용 서버 {asset}가 인터넷에 열려 있습니다.",
        "보안 설정이 느슨한 시험 서버를 통해 운영 데이터나 내부 정보가 새어 나갈 수 있습니다.",
        ("시험 서버는 사내 IP나 VPN에서만 열리게 합니다.", "디버그 모드를 끄고, 운영 데이터 복제본은 지웁니다."),
    ),
    20: Guide(
        "로그인 없이 열리는 운영·상태 페이지",
        "{asset} 서버의 운영·상태 확인 페이지가 로그인 없이 열립니다.",
        "환경 변수, 비밀번호, 접속자 IP 같은 내부 정보가 노출될 수 있습니다.",
        ("상태 확인 페이지를 끄거나 사내에서만 열리게 합니다.", "노출된 비밀번호가 있었다면 바꿉니다."),
    ),
    21: Guide(
        "다른 사이트가 응답을 읽을 수 있는 API 설정",
        "{asset} API가 아무 사이트에나 로그인 정보와 함께 응답을 읽도록 허용합니다.",
        "악성 사이트에 들어간 고객의 데이터를 몰래 읽어 갈 수 있습니다.",
        ("CORS 허용 목록을 우리 화면 주소로만 정합니다.", "들어온 Origin 값을 그대로 돌려주는 설정을 지웁니다."),
    ),
    23: Guide(
        "알려진 약점이 있는 서버 버전",
        "{asset} 서버가 알려진 약점이 있는 버전을 쓰는 것으로 보입니다.",
        "이미 공개된 공격 도구로 서버가 침입당할 수 있습니다.",
        ("서버 소프트웨어를 최신 보안 업데이트 버전으로 올립니다.", "응답 헤더에 버전이 나오지 않게 설정합니다."),
    ),
    25: Guide(
        "보안 업데이트가 끝난 서버 소프트웨어",
        "{asset} 서버가 제조사 지원이 끝난 버전을 쓰는 것으로 보입니다.",
        "새 약점이 나와도 고칠 방법이 없어 시간이 갈수록 위험해집니다.",
        ("지원 중인 버전으로 올리는 일정을 잡습니다.", "응답 헤더에 버전이 나오지 않게 설정합니다."),
    ),
    26: Guide(
        "암호화되지 않은 접속",
        "{asset} 서버가 HTTPS 없이 HTTP로만 열립니다.",
        "공용 와이파이 등에서 입력한 내용이 엿보일 수 있습니다.",
        ("인증서를 발급해 HTTPS를 켭니다.",),
    ),
    27: Guide(
        "HTTP로 들어오면 HTTPS로 옮기지 않음",
        "{asset} 서버에 HTTP로 접속하면 암호화된 주소로 옮겨 주지 않습니다.",
        "첫 접속 내용이 엿보이거나 바뀔 수 있습니다.",
        ("HTTP 요청을 HTTPS로 옮기는 301 전환을 웹 서버에 설정합니다.",),
    ),
    28: Guide(
        "문제가 있는 인증서",
        "{asset} 서버의 인증서가 곧 만료되거나 믿을 수 없는 인증서입니다.",
        "만료되면 고객 화면에 경고가 뜨고 서비스가 사실상 멈춥니다.",
        ("공인 인증 기관에서 인증서를 새로 발급합니다.", "자동 갱신을 설정합니다."),
    ),
    30: Guide(
        "브라우저 보안 설정 누락",
        "{asset} 등 서버 응답에 브라우저 보안 지시문(보안 헤더)이 빠져 있습니다.",
        "화면 위장이나 스크립트 공격에 더 쉽게 당할 수 있습니다.",
        ("웹 서버에 HSTS, CSP, X-Frame-Options 등 보안 헤더를 추가합니다.",),
    ),
    31: Guide(
        "보안 속성이 빠진 쿠키",
        "{asset} 서버가 보안 속성(Secure·HttpOnly·SameSite) 없이 쿠키를 내려줍니다.",
        "로그인 상태가 탈취돼 다른 사람이 회원으로 행세할 수 있습니다.",
        ("쿠키에 Secure, HttpOnly, SameSite 속성을 붙입니다.",),
    ),
    32: Guide(
        "우리 이름으로 가짜 메일을 보낼 수 있음",
        "메일 사칭을 막는 DNS 설정(SPF·DMARC)이 없거나 약합니다.",
        "회사 이름으로 지원자에게 피싱 메일을 보내 개인정보를 빼낼 수 있습니다.",
        ("SPF 레코드를 실제 메일 서버만 허용하도록 고칩니다(-all).", "DMARC 레코드를 p=quarantine 이상으로 추가합니다."),
    ),
    33: Guide(
        "곧 만료되는 도메인",
        "회사 도메인 사용 기간이 곧 끝납니다.",
        "만료 후 남이 도메인을 가져가면 회사 메일과 비밀번호 재설정 메일까지 받을 수 있습니다.",
        ("도메인 등록 업체에서 기간을 연장하고 자동 연장을 켭니다.", "도메인 이전 잠금을 켭니다."),
    ),
    34: Guide(
        "공개 키로 읽히는 백엔드 데이터",
        "화면 코드의 공개 키만으로 백엔드 대행 서비스 데이터를 읽을 수 있습니다.",
        "사용자 테이블 전체가 노출될 수 있습니다.",
        ("Supabase는 테이블마다 RLS를 켜고 정책을 추가합니다.", "Firebase는 보안 규칙에서 공개 읽기를 막습니다."),
    ),
}
