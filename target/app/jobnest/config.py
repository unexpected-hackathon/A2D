"""시연 설정: 도메인과 결함 토글.

결함 토글은 환경 변수 FIX_<점검번호>로 받는다. 0(기본)은 결함이 있는 상태,
1은 고친 상태다. 번호는 docs/A2D_점검점수설계.md의 #1~#34를 쓴다.
"""

import hashlib
import os

DOMAIN = os.environ.get("DEMO_DOMAIN", "jobnest.test").strip().strip(".").lower()

# 이름이 정해진 하위 자산. DNS 영역 파일과 인증서 SAN, 호스트 라우팅이 모두 이 표를 쓴다.
HOST_WWW = f"www.{DOMAIN}"
HOST_API = f"api.{DOMAIN}"
HOST_ADMIN = f"admin.{DOMAIN}"
HOST_STAGING = f"staging.{DOMAIN}"
HOST_DEV = f"dev.{DOMAIN}"
HOST_BOOKING = f"recruit.{DOMAIN}"  # 위탁 채용관리(ATS)로 가는 CNAME
HOST_PROMO = f"promo.{DOMAIN}"
HOST_TEST = f"test.{DOMAIN}"  # 감시 시연용: 나중에 새로 열리는 테스트 서버

# 우리 DNS가 가리키는 외부 주소(#4, #6, #14). 시연 DNS가 이 이름도 프록시로 돌려준다.
EXT_BOOKING = "jobnest.atspartner.test"
EXT_PAGES = "jobnest-promo.github.io"
EXT_BUCKET = "jobnest-resumes.s3.ap-northeast-2.amazonaws.com"

ALL_HOSTS = [
    DOMAIN,
    HOST_WWW,
    HOST_API,
    HOST_ADMIN,
    HOST_STAGING,
    HOST_DEV,
    HOST_BOOKING,
    HOST_PROMO,
    HOST_TEST,
    EXT_BOOKING,
    EXT_PAGES,
    EXT_BUCKET,
]

# 결함을 심은 점검 번호. demo.sh status와 README 표가 같은 목록을 쓴다.
FAULTS = {
    6: "하위 도메인 탈취 가능성 (promo CNAME → 해지된 GitHub Pages)",
    8: "백업·DB 덤프 파일 (www /backup.zip, /db.sql: 지원자·이력서 백업)",
    9: "설정 파일·소스 저장소 (/.env, /.git/HEAD)",
    10: "파일 목록 공개 (/uploads/: 이력서 파일)",
    11: "오류 메시지 정보 노출 (404에 스택 트레이스)",
    12: "화면 코드 속 비밀키 (/static/js/app.js)",
    13: "소스맵 공개 (/static/js/app.js.map)",
    14: "클라우드 저장소 공개 (이력서 S3 버킷 목록)",
    16: "인증 없는 API (api /api/v1/applicants, 숨은 www /internal/reports/export: 지원자 이메일·전화번호)",
    17: "API 설명서 공개 (api /swagger, /openapi.json)",
    18: "관리자 페이지 노출 (채용 담당자 콘솔: admin 하위 도메인, /admin)",
    19: "개발·테스트 서버 노출 (staging, dev)",
    20: "운영·상태 확인 페이지 (/server-status, /actuator/env)",
    21: "CORS 과다 허용 (api가 모든 Origin + 자격 증명 허용)",
    23: "서버 버전 표시 (Apache/2.4.49)",
    25: "지원 종료 버전 (PHP/8.1.2)",
    27: "HTTP → HTTPS 자동 전환 없음",
    28: "자체 서명·곧 만료되는 인증서",
    30: "보안 헤더 누락",
    31: "쿠키 보안 설정 누락",
    32: "메일 사칭 방지 (SPF +all, DMARC 없음)",
}


# 기본 시연 프로필(target/README.md): 이 결함만 켜고 나머지는 고친 상태로 둔다.
# 점검 직후 안전 점수 약 14(F, #16이 api·www 두 건) → #16 → #8 → #18을 고치면 30(F) → 49(D) → 100(A). (www C=4 기준)
DEMO_PRESET = (16, 8, 18)


def test_server() -> bool:
    """SHOW_TEST_SERVER=1이면 test 하위 도메인이 새로 열린다(감시·변화 감지 시연)."""
    return os.environ.get("SHOW_TEST_SERVER", "0").strip() in ("1", "true", "yes", "on")


def fixed(n: int) -> bool:
    """FIX_<n>=1이면 고친 상태."""
    return os.environ.get(f"FIX_{n}", "0").strip() in ("1", "true", "yes", "on")


def _fake(prefix: str, length: int, alphabet: str, salt: str) -> str:
    """git에 비밀키 형태 문자열을 남기지 않으려고 실행 시점에 결정적으로 만든다."""
    digest = hashlib.sha256(f"a2d-demo-{salt}".encode()).digest()
    out = []
    i = 0
    while len(out) < length:
        out.append(alphabet[digest[i % len(digest)] % len(alphabet)])
        i += 1
        if i % len(digest) == 0:
            digest = hashlib.sha256(digest).digest()
    return prefix + "".join(out)


UPPER_NUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# 가짜 비밀키(#12). 어떤 실제 서비스에도 유효하지 않다.
FAKE_AWS_KEY_ID = _fake("AKIA", 16, UPPER_NUM, "aws-id")
FAKE_AWS_SECRET = _fake("", 40, ALNUM, "aws-secret")
FAKE_STRIPE_SECRET = _fake("sk_live_", 24, ALNUM, "stripe")
