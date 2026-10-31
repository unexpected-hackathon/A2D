"""실제 대상을 읽기만 해서 점검하는 엔진(FR-02·FR-03, 상세설계 4절 "점검 1회의 실행 순서").

자산 찾기(#1~#4, #6)와 1차 점검을 정해진 순서로 돈다. LLM 없이 코드로만 동작한다.
대상에는 읽기(GET·DNS·TLS) 요청만 보내고, 발견은 ctx.add_finding으로 넘긴다. 증거는 가린 발췌만 넘긴다.

연결 통로(HTTP·DNS·TLS)는 engine.net의 구현을 쓰고, 테스트는 같은 자리에 가짜를 끼운다.
A2D_ENGINE=a2d.engine.live:LiveEngine 으로 가짜 엔진(fixture) 대신 끼운다.

자산 찾기는 단어 목록(#1), 화면·JS·robots·sitemap에 적힌 주소(#2·#3), 공개 인증서 발급 기록(#5, crt.sh.
예약 도메인은 묻지 않는다)으로 한다. 점검 전에 호스트마다 화면·robots·sitemap·JS에서 경로를 모아
#16(인증 없는 API)·#8(백업)·#10(파일 목록)이 고정 목록 밖의 경로도 보게 한다. 화면 코드에 설정이 적힌
Supabase·Firebase 프로젝트는 자산으로 등록해 공개 키로 읽히는지(#34, Storage는 #14) 본다. 테이블·컬렉션당
1건만 읽고, 상태를 바꿀 수 있는 이름(logout·delete 등)의 경로는 부르지 않는다.
숨은 경로를 단서로 따라가는 일(링크 두 단계 이상)은 Attack 에이전트가 맡는다.
#33 도메인 만료는 apps/api의 시연용 가짜 응답이 맡고, #7·#15·#22·#29는 2차다.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from dataclasses import dataclass, field

from ..config import Settings
from .base import Engine, EngineContext, EngineError, RawAsset, RawFinding
from .net import (CertInfo, Dns, DnsResolver, DnsUnavailable, Fetched, HttpClient, Tls, TlsInspector,
                  open_http_client)

log = logging.getLogger("a2d.engine.live")

# 자산 찾기에 쓰는 흔한 하위 도메인 이름(#1). 대상 DNS가 응답하는 것만 자산이 된다.
SUBDOMAIN_WORDS = ("www", "api", "admin", "staging", "dev", "test", "mail", "recruit", "promo",
                   "portal", "cms", "blog", "beta", "shop", "vpn", "git", "gitlab", "jenkins")

SECURITY_HEADERS = ("strict-transport-security", "content-security-policy", "x-frame-options")
# 공개돼 있으면 안 되는 운영 경로(#20). 환경 변수가 보이면 env, 상태·통계만 보이면 status.
STATUS_PATHS = ("/actuator/env", "/server-status", "/phpinfo.php", "/metrics",
                "/info.php", "/test.php", "/_ignition/health-check", "/telescope/requests", "/debug/vars")
# 외주·직접 운영 사이트에 흔히 남는 백업 이름. 도메인 이름을 딴 압축 파일(/jobnest.zip)도 따로 본다
BACKUP_PATHS = ("/backup.zip", "/backup.sql", "/db.sql", "/dump.sql", "/database.sql", "/backup.tar.gz",
                "/site.zip", "/www.zip", "/html.zip", "/web.zip", "/public_html.zip")
BACKUP_EXT = re.compile(r"\.(?:zip|sql|tar|tar\.gz|tgz|gz|bak|7z|rar|dump)$", re.I)
CONFIG_PATHS = (("/.env", "env"), ("/.env.local", "env"), ("/.env.production", "env"),
                ("/.env.development", "env"), ("/.env.bak", "env"), ("/.env.backup", "env"),
                ("/.git/HEAD", "git"), ("/.git/config", "git"),
                ("/.vscode/sftp.json", "sftp"), ("/sftp-config.json", "sftp"),
                ("/wp-config.php.bak", "config"), ("/wp-config.php~", "config"),
                ("/config.php.bak", "config"), ("/data/dbconfig.php.bak", "config"),
                ("/docker-compose.yml", "config"), ("/application.yml", "config"),
                ("/application.properties", "config"), ("/appsettings.json", "config"))
API_DOC_PATHS = ("/openapi.json", "/swagger.json", "/swagger", "/docs", "/api-docs")
# 흔한 관리자 로그인 경로(#18). /wp-admin/은 로그인 화면으로 넘기기만 해서(302) 로그인 화면 주소를 직접 본다.
ADMIN_PATHS = ("/admin", "/admin/", "/wp-login.php", "/phpmyadmin/", "/phpMyAdmin/", "/pma/",
               "/adm/", "/admin/login", "/administrator/", "/manager/", "/dashboard/login")
# 인증 없는 API(#16)에서 늘 먼저 보는 흔한 경로. 사이트에서 찾은 API 경로가 뒤에 붙는다.
DEFAULT_API_PATHS = ("/api/v1/applicants", "/api/v1/members", "/api/v1/users")

# 경로 찾기(#2·#3 확장): 호스트마다 화면·robots·sitemap·JS에서 API로 보이는 경로를 모아 #16에 넘긴다.
# 링크를 한 단계만 본다. 숨은 경로를 단서로 따라가는 일은 Attack 에이전트(추가 점검)가 맡는다.
JS_LIMIT = 8            # 호스트당 읽는 같은 호스트 JS 파일 수(#12 비밀키 점검과 같이 쓴다)
API_PROBE_LIMIT = 8     # 호스트당 #16으로 불러 보는 경로 수(흔한 경로 포함)
ROUTE_ROLES = ("web", "api", "dev")
_SCRIPT_SRC = re.compile(r'<script[^>]+src=["\']([^"\']+?\.m?js)(?:\?[^"\']*)?["\']', re.I)
_LINK_ATTR = re.compile(r'(?:href|src|action)=["\']([^"\'#\s]+)["\']', re.I)
_ROBOTS_PATH = re.compile(r"(?im)^\s*(?:dis)?allow:\s*(/\S*)")
_SITEMAP_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
# 코드 속 문자열로 적힌 API 경로("/api/v1/jobs", '/v2/users?page=1'). ${id} 같은 변수가 든 경로는 잡지 않는다.
_API_LITERAL = re.compile(r"""["'`](/(?:api|v\d+|rest|graphql)(?:/[A-Za-z0-9_.\-]*)*)(?:\?[^"'`\s]*)?["'`]""")
_API_URL = re.compile(r"""https?://([a-z0-9.\-]+)(/(?:api|v\d+|rest|graphql)(?:/[A-Za-z0-9_.\-]*)*)""", re.I)
_API_PREFIX = re.compile(r"^/(?:api|v\d+|rest|graphql)(?:/|$)", re.I)
# GET이라도 상태를 바꿀 수 있는 이름은 부르지 않는다(읽기 전용 원칙)
_UNSAFE_ROUTE = re.compile(r"log-?out|sign-?out|delete|remove|destroy|unsubscribe|reset|cancel|withdraw"
                           r"|revoke|pay|charge|send|confirm|activate|verify|callback|webhook", re.I)
_STATIC_EXT = re.compile(r"\.(?:m?js|css|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|map|pdf|zip|txt|xml)$", re.I)

_VENDOR_JS = re.compile(r"jquery|vendor|polyfill|framework|webpack|react-dom|bootstrap|analytics|gtag", re.I)

# 백엔드 대행 서비스(#34). 설정 값은 우리 화면 코드에 적힌 것만 쓴다(프로젝트 이름을 추측하지 않는다)
_SUPABASE_HOST = re.compile(r"\b([a-z0-9]{20})\.supabase\.co\b", re.I)
_SB_PUBLISHABLE = re.compile(r"\bsb_publishable_[A-Za-z0-9_-]{20,}")
_FB_PROJECT = re.compile(r"""projectId["']?\s*[:=]\s*["']([a-z0-9-]{4,40})["']""")
_FB_DB_URL = re.compile(r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)?\.(?:firebaseio\.com|firebasedatabase\.app)", re.I)
_FB_BUCKET = re.compile(r"""storageBucket["']?\s*[:=]\s*["']([a-z0-9.\-]+\.(?:appspot\.com|firebasestorage\.app))["']""")
# 테이블 목록을 못 받을 때 볼 흔한 이름. 개인정보가 있을 법한 이름을 먼저 본다
_COMMON_TABLES = ("users", "profiles", "customers", "members", "accounts", "orders", "applicants",
                  "contacts", "leads", "bookings", "reservations", "payments", "messages", "posts")
_PII_TABLE = re.compile(r"user|profile|customer|member|account|order|applicant|contact|lead|booking"
                        r"|reservation|payment|patient|student|employee|subscriber", re.I)
SUPABASE_TABLE_LIMIT = 8
_DEV_WORDS = {"staging", "stg", "stage", "dev", "develop", "test", "qa", "beta", "sandbox", "preview"}
FIRESTORE_COLLECTION_LIMIT = 6

# 인증서 발급 기록(#5). 대상 서버가 아니라 공개 CT 로그(crt.sh)에 한 번 묻는다.
CT_LOG_URL = "https://crt.sh/?q=%25.{domain}&output=json"
CT_TIMEOUT = 20.0       # crt.sh는 느릴 때가 많다. 넘으면 #5 없이 진행한다
CT_NAME_LIMIT = 30      # CT에서 찾은 이름 중 DNS로 확인할 최대 수
_CT_NAME = re.compile(r'"(?:name_value|common_name)"\s*:\s*"([^"]+)"')
# 예약 도메인(RFC 2606·6761)은 CT 로그에 없다. 시연(.test)에서는 묻지 않는다
_RESERVED_TLDS = (".test", ".example", ".invalid", ".localhost", ".local", ".internal")

# 비밀키 앞부분 형태(#12). 값은 저장하지 않고 '있다'만 센다.
SECRET_PATTERNS = {
    "AWS 액세스 키": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Stripe 비밀키": re.compile(r"\bsk_live_[0-9A-Za-z]{10,}"),
    "토스페이먼츠 키": re.compile(r"\blive_sk_[0-9A-Za-z]{10,}"),
    "Slack 토큰": re.compile(r"\bxox[bp]-[0-9A-Za-z-]{10,}"),
    "GitHub 토큰": re.compile(r"\b(?:ghp_|github_pat_)[0-9A-Za-z_]{20,}"),
    "OpenAI 키": re.compile(r"\bsk-(?:proj-|svcacct-|admin-)[0-9A-Za-z_-]{10,}|\bsk-[A-Za-z0-9]{48}\b"),
    "Anthropic 키": re.compile(r"\bsk-ant-[0-9A-Za-z_-]{10,}"),
    "개인 키 파일": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    # 바이브코딩 앱에서 자주 새는 AI·메일·메신저 키. 앞부분 형태가 고유한 것만 넣는다
    "OpenRouter 키": re.compile(r"\bsk-or-v1-[0-9a-f]{40,}"),
    "Groq 키": re.compile(r"\bgsk_[A-Za-z0-9]{40,}"),
    "xAI 키": re.compile(r"\bxai-[A-Za-z0-9]{40,}"),
    "Hugging Face 토큰": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "Replicate 토큰": re.compile(r"\br8_[A-Za-z0-9]{30,}"),
    "Supabase 비밀키": re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}"),
    "SendGrid 키": re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),
    "Twilio 키": re.compile(r"\bSK[0-9a-f]{32}\b"),
    "Mailgun 키": re.compile(r"\bkey-[0-9a-f]{32}\b"),
    "Slack 웹훅": re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]{16,}"),
    "Discord 웹훅": re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]{20,}"),
    "텔레그램 봇 토큰": re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"),
    "Google 서비스 계정 키": re.compile(r"\"type\"\s*:\s*\"service_account\""),
}
# 비밀번호가 든 DB 접속 주소(postgres://user:pass@host). 예시 값과 내 컴퓨터 주소는 세지 않는다
_DB_URL = re.compile(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|rediss?|amqps?)://"
                     r"([^\s:@/'\"`]+):([^\s@/'\"`]+)@([^\s/:'\"`]+)")
_DB_URL_DUMMY_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "host", "db", "hostname")
_DB_URL_DUMMY_PASS = ("password", "pass", "secret", "pwd", "changeme", "****", "xxxx")
# 문서·예제에 쓰는 자리표시 키(AWS 문서의 AKIAIOSFODNN7EXAMPLE 등)는 비밀키로 보지 않는다(점검점수설계 #12 조건).
_PLACEHOLDER = re.compile(r"example|sample|dummy|placeholder|your[_-]?|x{6,}", re.I)
# Supabase 키는 JWT라 앞부분이 공개 키(anon)와 같다. 본문(payload)의 role이 service_role일 때만 비밀키다.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.(eyJ[A-Za-z0-9_-]{8,})\.[A-Za-z0-9_-]{8,}")
_SOURCEMAP_URL = re.compile(r"[#@]\s*sourceMappingURL=([^\s'\"*]+)")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")  # 숫자 경계: 주문번호·타임스탬프 오탐 방지
_PII_KEYS = {"email", "phone", "mobile", "tel", "name", "username", "birth", "birthday",
             "rrn", "ssn", "resident", "address", "resume", "applicant"}
# 목록·파일 이름이 민감해 보이는지(#10·#14)
SENSITIVE_NAME = re.compile(r"(resume|이력서|applicant|지원자|backup|백업|dump|export|\.sql|\.csv|members?|users?|personal)", re.I)
_HREF = re.compile(r'https?://([a-z0-9.\-]+)', re.I)
# 우리 사이트가 가리키는 클라우드 저장소 버킷(#14). 이름을 추측하지 않고 코드에 나온 것만 본다.
_CLOUD_HOST = re.compile(r'([a-z0-9.\-]+\.s3[a-z0-9.\-]*\.amazonaws\.com|[a-z0-9.\-]+\.blob\.core\.windows\.net|[a-z0-9.\-]+\.kr\.object\.ncloudstorage\.com)', re.I)
_GENERATOR = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']{1,60})', re.I)
_JQUERY = re.compile(r"jquery[.@-]?v?(\d+\.\d+\.\d+)", re.I)
_GENERATOR_VERSION = re.compile(r"^(.+?)\s+v?(\d+(?:\.\d+)*)\s*$")
# 버전은 몰라도 쓰는 것만은 알 수 있는 부품(#24 식별 범위: 기존 방식 + 바이브코딩 방식)
_FRAMEWORK_MARKS = (
    ("WordPress", ("/wp-content/", "/wp-includes/")),
    ("그누보드", ("g5_url", "/gnuboard")),
    ("영카트", ("g5_shop_url", "youngcart")),
    ("라이믹스", ("rhymix",)),
    ("Next.js", ("/_next/static/", "__next_data__")),
    ("Nuxt", ("/_nuxt/", "window.__nuxt__")),
    ("React", ("data-reactroot", "react-dom")),
    ("Supabase", (".supabase.co",)),
    ("Firebase", ("firebaseapp.com", "firebaseio.com", "firebasejs")),
)
_PRODUCT_NAMES = {"apache": "Apache", "php": "PHP", "nginx": "nginx", "openssl": "OpenSSL",
                  "iis": "IIS", "express": "Express"}
# 서버 소프트웨어 버전을 읽을 자산(TLS 버전·인증서도 자산 찾기에서 한 번만 본다)
TLS_ROLES = ("web", "api", "admin", "dev")

# 내장한 취약 버전 목록(#23). 실제 서비스라면 주기적으로 갱신한다.
KNOWN_VULNS = {
    ("apache", "2.4.49"): [{"id": "CVE-2021-41773", "cvss": 7.5, "kev": True}],
    ("apache", "2.4.50"): [{"id": "CVE-2021-42013", "cvss": 9.8, "kev": True}],
}
# 지원 종료 소프트웨어(#25). endoflife.date를 내장했다고 가정한 최소 표.
EOL = {("php", "8.1"), ("php", "8.0"), ("php", "7.4"), ("openssl", "1.1")}

EVIDENCE_LIMIT = 200
DNS_FAILURE_LIMIT = 3  # DNS가 연달아 이만큼 답하지 않으면 자산 찾기를 그만둔다(시간 초과가 쌓이지 않게)
REACH_PROBE_LIMIT = 3  # 자산 찾기에서 응답이 하나도 없을 때 더 두드려 볼 자산 수


@dataclass
class Asset:
    host: str
    alias: str
    role: str  # web | api | admin | dev | external | dangling | mail
    importance: int
    importance_rule: str
    found_by: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    components: list[dict] = field(default_factory=list)  # #24 {"name", "version", "eol"}
    cert: CertInfo | None = None  # 자산 찾기에서 본 인증서. #28이 다시 연결하지 않고 쓴다
    baas: dict | None = None  # #34 Supabase·Firebase 설정(화면 코드에서 읽은 공개 값)


def _clip(text: str) -> str:
    return text[:EVIDENCE_LIMIT]


class LiveEngine(Engine):
    def __init__(self, settings: Settings, *, dns: Dns | None = None, tls: Tls | None = None,
                 client=None, host_min_interval: float | None = None):
        self.s = settings
        self._dns = dns if dns is not None else DnsResolver(settings.dns_servers)
        # 점검 DNS를 정했으면 HTTP·TLS 접속도 같은 DNS로 주소를 찾는다(자산 찾기와 접속이 같은 곳을 보게)
        self._resolve = self._dns.a if settings.dns_servers else None
        # A2D_CA_BUNDLE은 #28이 인증서 발급 체인을 검증할 때만 쓴다. 내용 조회는 검증하지 않는다(net.open_http_client)
        self._tls = tls if tls is not None else TlsInspector(resolve=self._resolve,
                                                             ca_bundle=settings.ca_bundle or None)
        self._client = client            # 테스트에서 httpx.MockTransport를 끼운다
        self._owns_client = client is None
        self._interval = host_min_interval

    async def run(self, ctx: EngineContext) -> None:
        client = self._client or open_http_client(resolve=self._resolve)
        interval = self._interval if self._interval is not None else None
        http = HttpClient(ctx.budget, client) if interval is None else \
            HttpClient(ctx.budget, client, host_min_interval=interval)
        try:
            ctx.set_stage("discovering", "자산을 찾는 중", 0, 1)
            assets = await self._discover(ctx, http)
            if not assets:
                raise EngineError("이 도메인에서 주소가 있는 호스트를 찾지 못해 점검하지 못했습니다. "
                                  "도메인의 DNS 레코드를 확인해 주세요.")
            await self._ensure_reachable(http, assets)
            ctx.set_stage("discovering", "자산을 찾는 중", 1, 1)

            # 같은 서비스를 가리키는 꼭짓점·www 자산에 점검이 겹치지 않게, 대표 웹 자산 하나만 깊게 본다.
            domain = ctx.domain.lower().strip(".")
            web_assets = [a for a in assets if a.role == "web"]
            primary = next((a for a in web_assets if a.host == f"www.{domain}"),
                           web_assets[0] if web_assets else None)
            primary_host = primary.host if primary else None
            # 호스트마다 화면·robots·sitemap·JS에서 경로를 모은다(#16 인증 없는 API, #8·#10 숨긴 경로)
            routes = await self._collect_routes(http, assets, domain, primary_host)

            total = len(assets)
            ctx.set_stage("checking", "노출을 점검하는 중", 0, total + 1)
            done = 0
            server_wide_host = primary_host or next((a.host for a in assets
                                                     if a.role in ("api", "admin")), None)
            # 관리자 하위 도메인을 먼저 본다. 거기서 로그인 화면이 열려 있으면 www의 관리자 경로는 다시 세지 않고,
            # 하위 도메인이 막혀 있으면 www 경로를 본다(하위 도메인이 '있다'가 아니라 '열려 있다'가 기준).
            admin_login_found = False
            for a in sorted(assets, key=lambda x: x.role != "admin"):
                ctx.budget.check()
                found = await self._check_asset(ctx, http, a, primary_host=primary_host, routes=routes,
                                                run_server_wide=a.host == server_wide_host,
                                                admin_login_found=admin_login_found)
                admin_login_found = admin_login_found or found
                done += 1
                ctx.set_stage("checking", "노출을 점검하는 중", done, total + 1)
            await self._check_mail(ctx)  # #32 (DNS)
            ctx.set_stage("checking", "노출을 점검하는 중", total + 1, total + 1)
        finally:
            if self._owns_client:
                await client.aclose()

    # ================================================================ 자산 찾기

    async def _discover(self, ctx: EngineContext, http: HttpClient) -> list[Asset]:
        domain = ctx.domain.lower().strip(".")
        found: dict[str, Asset] = {}

        # #1 하위 도메인 찾기 + 꼭짓점 도메인. DNS는 블로킹이라 스레드로 보내고, 사이사이 중지를 확인한다.
        # DNS가 답하지 않으면 '없음'으로 넘기지 않고, 연달아 실패하면 점검을 실패로 끝낸다.
        failures = 0
        for host in [domain] + [f"{w}.{domain}" for w in SUBDOMAIN_WORDS]:
            ctx.budget.check()
            try:
                cname = await asyncio.to_thread(self._dns.cname, host)
                addrs = await asyncio.to_thread(self._dns.a, host)
            except DnsUnavailable as e:
                failures += 1
                log.info("DNS 무응답(%d/%d): %s", failures, DNS_FAILURE_LIMIT, e)
                if failures >= DNS_FAILURE_LIMIT:
                    raise EngineError("도메인의 DNS 서버가 응답하지 않아 점검하지 못했습니다. "
                                      "잠시 뒤 다시 시도해 주세요.") from e
                continue
            failures = 0
            if not cname and not addrs:
                continue
            found[host] = self._classify(host, domain, cname)
            found[host].found_by.append(1)

        # #2 홈페이지 링크 + #3 robots·sitemap: 같은 도메인 아래 추가 호스트를 더 찾는다
        # #5 인증서 발급 기록: 단어 목록에 없는 하위 도메인(api-prod, partner 등)을 공개 CT 로그에서 찾는다
        for host in await self._ct_names(http, domain):
            if host in found:
                if 5 not in found[host].found_by:
                    found[host].found_by.append(5)
                continue
            try:
                cname = await asyncio.to_thread(self._dns.cname, host)
                addrs = [] if cname else await asyncio.to_thread(self._dns.a, host)
            except DnsUnavailable as e:
                log.info("DNS 무응답, 인증서 기록으로 찾은 호스트를 건너뜀: %s", e)
                continue
            if cname or addrs:
                found[host] = self._classify(host, domain, cname)
                found[host].found_by.append(5)

        web_host = f"www.{domain}" if f"www.{domain}" in found else domain
        extra_hosts: set[str] = set()
        home = await http.get_cached(f"https://{web_host}/")
        cloud_hosts: set[str] = set()
        baas: dict[str, dict] = {}
        if home is not None:
            # 화면과 화면이 불러오는 JS에 적힌 주소: 같은 도메인의 다른 서버, 클라우드 저장소, Supabase·Firebase
            texts = [home.text] + [js.text for js in await self._scripts(http, web_host, home)]
            for text in texts:
                extra_hosts |= self._hosts_in(text, domain)
                cloud_hosts |= {m.group(1).lower() for m in _CLOUD_HOST.finditer(text)}
                _collect_baas(text, baas)
            if web_host in found:
                found[web_host].found_by.append(2)
                found[web_host].components = _identify_components(home)  # #24
        robots = await http.get_cached(f"https://{web_host}/robots.txt")
        sitemap = await http.get_cached(f"https://{web_host}/sitemap.xml")
        for doc in (robots, sitemap):
            if doc is not None and doc.status == 200:
                extra_hosts |= self._hosts_in(doc.text, domain)
                if web_host in found and 3 not in found[web_host].found_by:
                    found[web_host].found_by.append(3)
        for host in extra_hosts:
            if host in found:
                if 2 not in found[host].found_by:
                    found[host].found_by.append(2)
                continue
            if not host.endswith("." + domain):
                continue
            try:
                cname = await asyncio.to_thread(self._dns.cname, host)
                addrs = [] if cname else await asyncio.to_thread(self._dns.a, host)
            except DnsUnavailable as e:
                log.info("DNS 무응답, 링크로 찾은 호스트를 건너뜀: %s", e)
                continue
            if cname or addrs:
                found[host] = self._classify(host, domain, cname)
                found[host].found_by.append(2)

        # #14 클라우드 저장소: 우리 사이트가 가리키는 버킷만 자산으로 등록한다(이름 추측 금지).
        for host in sorted(cloud_hosts):
            if host not in found:
                found[host] = Asset(host, host.split(".")[0], "cloud", 5,
                                    "우리 사이트가 쓰는 클라우드 저장소", found_by=[14], tags=["cloud"])

        # #34 백엔드 대행 서비스: 우리 화면 코드에 설정이 적힌 프로젝트만 자산으로 등록한다
        for host, conf in sorted(baas.items()):
            if host not in found:
                found[host] = Asset(host, conf["alias"], "baas", 5,
                                    "우리 화면 코드가 쓰는 백엔드 대행 서비스", found_by=[34], tags=["baas"],
                                    baas=conf)

        # 인증서·TLS 버전: 우리 서버 자산마다 한 번씩, 동시에 본다(자산 정보 표시와 #28이 함께 쓴다)
        ctx.budget.check()
        tls_assets = [a for a in found.values() if a.role in TLS_ROLES]
        certs = await asyncio.gather(*(asyncio.to_thread(self._tls.inspect, a.host) for a in tls_assets))
        for a, cert in zip(tls_assets, certs):
            a.cert = cert

        # 등록. 외부 ATS(#4 recruit)는 식별만 하고 자산 메모로 남긴다.
        assets = sorted(found.values(), key=lambda a: (self._role_order(a.role), a.host))
        for a in assets:
            tls_version = _tls_label(a.cert.tls_version) if a.cert and not a.cert.error else None
            ctx.add_asset(RawAsset(host=a.host, alias=a.alias, url=f"https://{a.host}/",
                                   found_by=sorted(set(a.found_by)), tags=a.tags,
                                   importance=a.importance, importance_rule=a.importance_rule,
                                   components=a.components, tls_version=tls_version))
        return assets

    async def _ensure_reachable(self, http: HttpClient, assets: list[Asset]) -> None:
        """대상에 하나도 닿지 못하면 점검을 실패로 끝낸다. 아무것도 못 본 점검이 100점(A)이 되지 않게 한다.

        자산 찾기에서 응답을 받았으면 바로 넘어간다. 홈페이지가 없는 도메인(API만 있는 경우 등)도 있어,
        응답이 없을 때만 다른 자산 몇 개의 첫 화면을 더 두드려 본다.
        """
        if http.responses:
            return
        for a in [a for a in assets if a.role in ("web", "api", "admin", "dev")][:REACH_PROBE_LIMIT]:
            await http.get(f"https://{a.host}/")
            if http.responses:
                return
        raise EngineError("대상 서버에 연결하지 못해 점검하지 못했습니다. 서버가 켜져 있는지, "
                          "점검 서버에서 도메인 주소를 찾을 수 있는지(DNS 설정) 확인해 주세요.")

    def _classify(self, host: str, domain: str, cname: str | None) -> Asset:
        label = host[:-len(domain) - 1] if host != domain else ""
        ext = cname and not cname.endswith("." + domain) and cname != domain
        if ext:
            # 우리 DNS가 외부를 가리킨다(#4 위탁 서비스, #6 하위 도메인 탈취 후보)
            if "github.io" in cname or "pages" in cname:
                return Asset(host, label or host, "dangling", 3, "외부 서비스로 연결된 하위 도메인",
                             tags=["external"])
            return Asset(host, label or host, "external", 2, "외부 위탁 서비스로 연결(CNAME)",
                         tags=["external"])
        # 인증서 기록(#5)으로 찾은 이름은 api-prod·admin2·dev-api처럼 붙어 있어 낱말 단위로 본다
        words = set(re.split(r"[-.\d]+", label)) - {""}
        if label in ("api",) or (words & {"api", "backend", "gateway"} and not words & _DEV_WORDS):
            return Asset(host, label, "api", 5, "개인정보를 다루는 API로 추정", tags=["api"])
        if label in ("admin",) or words & {"admin", "adm", "manager", "backoffice", "console"}:
            return Asset(host, label, "admin", 4, "관리자·내부 도구", tags=["admin"])
        if label in ("staging", "dev", "test", "beta") or words & _DEV_WORDS:
            return Asset(host, label, "dev", 3, "개발·테스트 서버", tags=["dev"])
        if label in ("", "www"):
            return Asset(host, label or host, "web", 4, "대표 홈페이지", tags=["web"])
        if label == "mail":
            return Asset(host, label, "mail", 1, "메일 호스트", tags=["mail"])
        return Asset(host, label, "web", 3, "일반 하위 서비스")

    @staticmethod
    def _role_order(role: str) -> int:
        return {"web": 0, "api": 1, "admin": 2, "dev": 3, "dangling": 4, "external": 5,
                "cloud": 6, "mail": 7}.get(role, 9)

    @staticmethod
    def _hosts_in(text: str, domain: str) -> set[str]:
        return {m.group(1).lower() for m in _HREF.finditer(text)
                if m.group(1).lower().endswith("." + domain) or m.group(1).lower() == domain}

    # ================================================================ 점검

    async def _check_asset(self, ctx: EngineContext, http: HttpClient, a: Asset,
                           *, primary_host: str | None, run_server_wide: bool,
                           admin_login_found: bool = False, routes: dict[str, list[str]] | None = None) -> bool:
        """자산 하나를 점검한다. 관리자 로그인 화면(#18)을 찾았으면 True."""
        if a.role == "external":
            return False  # #4 식별만. 3자 서비스는 점검하지 않는다
        if a.role == "dangling":
            await self._check_dangling(ctx, http, a)
            return False
        if a.role == "cloud":
            await self._check_bucket(ctx, http, a)  # #14
            return False
        if a.role == "baas":
            await self._check_baas(ctx, http, a)  # #34 (+ Firebase Storage는 #14)
            return False
        if a.role == "mail":
            return False
        admin_found = False
        paths = (routes or {}).get(a.host, [])

        if a.role == "web" and a.host == primary_host:  # 대표 웹 자산에서만(꼭짓점·www 중복 방지)
            # 없는 주소부터 본다. 그 응답(모르는 경로를 index로 돌려주는 SPA 등)을 아래 경로 점검이 걸러 쓴다.
            catch_all = await self._check_error_page(ctx, http, a)  # #11
            await self._check_files(ctx, http, a, catch_all, paths)  # #8 #9 #10
            await self._check_frontend(ctx, http, a)    # #12 #13 #24
            await self._check_status_pages(ctx, http, a, catch_all)  # #20
            if not admin_login_found:  # 관리자 하위 도메인에서 이미 찾았으면 한 번만 센다
                admin_found = await self._check_admin_path(ctx, http, a, catch_all)  # #18 (www/admin 등)
            await self._check_cookie(ctx, http, a)      # #31
            await self._check_unauth_api(ctx, http, a, paths, defaults=True)  # #16 (Next.js 등 같은 서버의 /api)
            await self._check_graphql(ctx, http, a)     # #17
        if a.role == "api":
            doc = await self._check_api_docs(ctx, http, a)  # #17
            await self._check_unauth_api(ctx, http, a, paths, defaults=True, api_doc=doc)  # #16
            await self._check_graphql(ctx, http, a)     # #17
            await self._check_cors(ctx, http, a)        # #21
        if a.role == "web" and a.host != primary_host and a.host not in (ctx.domain, f"www.{ctx.domain}"):
            await self._check_unauth_api(ctx, http, a, paths)  # #16 다른 하위 서비스(shop. 등)는 찾은 경로만
        if a.role == "admin":
            admin_found = await self._check_admin_host(ctx, http, a)  # #18
        if a.role == "dev":
            await self._check_dev_server(ctx, http, a)  # #19
            await self._check_unauth_api(ctx, http, a, paths)  # #16 개발 서버가 쓰는 API(찾은 경로만)

        if run_server_wide and a.role in ("web", "api", "admin"):
            await self._check_server_wide(ctx, http, a)  # #23 #25 #30 #27 #28
        return admin_found

    # ---------------------------------------------------------------- #8 #9 #10
    async def _check_files(self, ctx, http, a: Asset, catch_all: Fetched | None = None,
                           paths: list[str] | None = None) -> None:
        # 흔한 백업 이름 + 도메인 이름을 딴 압축 파일 + robots·링크에 적힌 압축·덤프 파일
        label = ctx.domain.lower().strip(".").split(".")[0]
        found_files = [p for p in (paths or []) if BACKUP_EXT.search(p)]
        backup_paths = list(dict.fromkeys([*BACKUP_PATHS, f"/{label}.zip", f"/{label}.sql", *found_files]))
        for path in backup_paths:
            r = await http.get_cached(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and _looks_like_file(r):
                self._add(ctx, a, 8, "confirmed", f"GET {r.url}",
                          f"{path} 200 응답, 파일 형식 확인(가림)")
                break  # 자산당 한 건
        reported: set[str] = set()
        for path, situation in CONFIG_PATHS:
            if situation in reported:
                continue  # 같은 저장소(.git)는 한 건으로 센다
            r = await http.get(f"https://{a.host}{path}")
            if (r is not None and r.status == 200 and not _same_as(r, catch_all)
                    and _config_file_matches(path, r)):
                self._add(ctx, a, 9, situation, f"GET {r.url}", f"{path} 200 응답, 파일 형식 확인(가림)")
                reported.add(situation)
        # 파일 목록(#10): 흔한 업로드 폴더 + robots·링크에 적힌 폴더. 자산당 한 건(가장 민감한 것)
        dirs = ["/uploads/", "/upload/", "/files/", "/data/", "/backup/"]
        dirs += [p for p in (paths or []) if p.endswith("/") and p != "/"]
        listing: Fetched | None = None
        for path in list(dict.fromkeys(dirs))[:12]:
            r = await http.get_cached(f"https://{a.host}{path}")
            if r is None or r.status != 200 or "index of" not in r.text.lower():
                continue
            if listing is None or (SENSITIVE_NAME.search(r.text) and not SENSITIVE_NAME.search(listing.text)):
                listing = r
        if listing is not None:
            situation = "sensitive" if SENSITIVE_NAME.search(listing.text) else "basic"
            self._add(ctx, a, 10, situation, f"GET {listing.url}", "디렉터리 목록 공개(파일 이름 가림)")

    # ---------------------------------------------------------------- #11
    async def _check_error_page(self, ctx, http, a: Asset) -> Fetched | None:
        """#11을 보고, 없는 주소에 200으로 답하면 그 응답을 돌려준다(이후 경로 점검의 비교 기준)."""
        r = await http.get(f"https://{a.host}/a2d-check-{_token()}")
        if r is None:
            return None
        low = r.text.lower()
        if r.status >= 500 or "traceback" in low or "stack trace" in low or "sqlalchemy" in low:
            self._add(ctx, a, 11, "basic", f"GET {r.url}",
                      f"없는 주소에 오류 {r.status}, 내부 코드 기록·경로 노출(가림)")
        return r if r.status == 200 else None

    # ---------------------------------------------------------------- #12 #13 #24
    async def _check_frontend(self, ctx, http, a: Asset) -> None:
        home = await http.get_cached(f"https://{a.host}/")
        if home is None:
            return
        # 화면 HTML 안의 스크립트(Next.js의 __NEXT_DATA__, 인라인 설정)도 비밀키를 본다
        inline = _secret_kinds(home.text) if home.status == 200 else []
        if inline:
            self._add(ctx, a, 12, "secret", f"GET {home.url}",
                      _clip(f"화면 HTML에 {'·'.join(inline)} 형태 키 노출(가림)"))
        for js in await self._scripts(http, a.host, home):
            url = js.url
            kinds = _secret_kinds(js.text)
            if inline:
                kinds = [k for k in kinds if k not in inline]
            if kinds:
                self._add(ctx, a, 12, "secret", f"GET {js.url}",
                          _clip(f"화면 코드에 {'·'.join(kinds)} 형태 키 노출(가림)"))
            map_url = _sourcemap_url(js.text, url)
            if map_url is None or not map_url.startswith(f"https://{a.host}/"):
                continue  # 소스맵이 없거나, 코드 안에 들어 있거나(data:), 다른 곳에 있다
            mapr = await http.get(map_url)
            if mapr is None or mapr.status != 200 or not _is_sourcemap(mapr):
                continue  # 모르는 경로를 index.html로 돌려주는 SPA는 소스맵 공개가 아니다
            # 열린 소스맵은 #13(낮음)으로 남기고, 안의 비밀키는 #12로 따로 보고한다(점검점수설계 #13).
            # 같은 키가 코드와 소스맵에 다 있으면 #12는 코드 쪽 한 건으로 센다.
            self._add(ctx, a, 13, "basic", f"GET {mapr.url}", "소스맵(.map) 공개")
            msecret = _secret_kinds(mapr.text)
            if msecret and not kinds:
                self._add(ctx, a, 12, "secret", f"GET {mapr.url}",
                          _clip(f"소스맵 안에 {'·'.join(msecret)} 형태 키 노출(가림)"))

    # ---------------------------------------------------------------- #20
    async def _check_status_pages(self, ctx, http, a: Asset, catch_all: Fetched | None = None) -> None:
        for path in STATUS_PATHS:
            r = await http.get(f"https://{a.host}{path}")
            if r is None or r.status != 200 or _same_as(r, catch_all) or not _status_page_matches(path, r):
                continue
            low = r.text.lower()
            # 환경 변수 목록(actuator)이거나 phpinfo에 비밀값이 보이면 env. 통계만 보이면 status
            php = path in ("/phpinfo.php", "/info.php", "/test.php")
            if path in ("/actuator/env", "/_ignition/health-check", "/telescope/requests") or \
                    (php and ("password" in low or "secret" in low)):
                self._add(ctx, a, 20, "env", f"GET {r.url}", f"{path} 공개, 환경 변수·비밀값 노출(가림)")
            else:
                self._add(ctx, a, 20, "status", f"GET {r.url}", f"{path} 공개, 서버 상태·통계 노출")

    # ---------------------------------------------------------------- #18
    async def _check_admin_path(self, ctx, http, a: Asset, catch_all: Fetched | None = None) -> bool:
        for path in ADMIN_PATHS:
            r = await http.get(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and not _same_as(r, catch_all) and _is_login(r.text):
                self._add(ctx, a, 18, "basic", f"GET {r.url}", f"{path}에 관리자 로그인 화면 노출")
                return True
        return False

    async def _check_admin_host(self, ctx, http, a: Asset) -> bool:
        r = await http.get(f"https://{a.host}/")
        if r is not None and r.status == 200 and _is_login(r.text):
            self._add(ctx, a, 18, "basic", f"GET {r.url}", "관리자 로그인 화면이 외부에 노출")
            return True
        return False

    # ---------------------------------------------------------------- #19
    async def _check_dev_server(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"https://{a.host}/")
        if r is None or r.status != 200:
            return
        low = r.text.lower()
        debug = "debug=true" in low.replace(" ", "") or "debug" in low and "banner" in low
        dbg = await http.get(f"https://{a.host}/debug/vars")
        has_debug = debug or (dbg is not None and dbg.status == 200)
        situation = "debug" if has_debug else "basic"
        self._add(ctx, a, 19, situation, f"GET {r.url}",
                  "개발·테스트 서버 외부 노출" + (", 디버그 표시 있음" if has_debug else ""))

    # ---------------------------------------------------------------- #16
    async def _check_unauth_api(self, ctx, http, a: Asset, paths: list[str] | None = None, *,
                                defaults: bool = False, api_doc: Fetched | None = None) -> None:
        """로그인 없이 부른 API가 개인정보 형태를 돌려주는지. 자산당 한 건.

        부를 경로: (흔한 경로) + API 설명서의 GET 경로 + 화면·JS·robots·sitemap에서 찾은 경로.
        API처럼 보이는 경로를 먼저 부르고, 상태를 바꿀 수 있는 이름(logout·delete 등)은 부르지 않는다.
        """
        candidates: list[str] = list(DEFAULT_API_PATHS) if defaults else []
        if api_doc is not None:
            candidates += _openapi_get_paths(api_doc)
        found = [p for p in (paths or []) if _probe_worthy(p)]
        candidates += sorted(found, key=lambda p: (0 if _API_PREFIX.match(p) else 1, p))  # 순서가 매번 같게
        for path in list(dict.fromkeys(candidates))[:API_PROBE_LIMIT]:
            r = await http.get_cached(f"https://{a.host}{path}")
            if r is None or r.status != 200:
                continue
            kinds, count = _pii_shape(r)
            if kinds:
                where = f"{count}건" if count is not None else "데이터"
                self._add(ctx, a, 16, "pii", f"GET {r.url}",
                          _clip(f"{r.status} 응답, {where}에 {'·'.join(kinds)} 형식 포함(가림)"))
                return

    # ---------------------------------------------------------------- #17
    async def _check_api_docs(self, ctx, http, a: Asset) -> Fetched | None:
        for path in API_DOC_PATHS:
            r = await http.get(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and _is_api_doc(r):
                self._add(ctx, a, 17, "basic", f"GET {r.url}", f"{path} API 설명서 공개")
                return r
        return None

    async def _check_graphql(self, ctx, http, a: Asset) -> None:
        """GraphQL 스키마 조회(introspection)가 열려 있는지. 읽기 질의 하나를 GET으로 보낸다."""
        for path in ("/graphql", "/api/graphql", "/v1/graphql"):
            r = await http.get(f"https://{a.host}{path}?query=%7B__schema%7BqueryType%7Bname%7D%7D%7D")
            if r is not None and r.status == 200 and '"__schema"' in r.text and not _is_html(r):
                self._add(ctx, a, 17, "graphql", f"GET {r.url}", f"{path} GraphQL 스키마 조회 공개")
                return

    # ================================================================ 경로 찾기

    async def _scripts(self, http, host: str, home: Fetched) -> list[Fetched]:
        """화면이 불러오는 같은 호스트의 JS(앱 코드 먼저, 라이브러리 나중). 받은 JS는 점검 동안 재사용한다."""
        srcs: list[str] = []
        for src in _SCRIPT_SRC.findall(home.text):
            if src.startswith("//"):
                src = "https:" + src
            url = src if src.startswith("http") else f"https://{host}{_abs(src)}"
            if url.startswith(f"https://{host}/") and url not in srcs:
                srcs.append(url)
        srcs.sort(key=lambda u: 1 if _VENDOR_JS.search(u) else 0)
        out = []
        for url in srcs[:JS_LIMIT]:
            js = await http.get_cached(url)
            if js is not None and js.status == 200 and not _is_html(js):
                out.append(js)
        return out

    async def _collect_routes(self, http, assets: list[Asset], domain: str,
                              primary_host: str | None) -> dict[str, list[str]]:
        """호스트마다 경로를 모은다. 화면 링크, robots.txt의 Disallow·Allow, sitemap, JS 속 API 경로.

        JS가 다른 우리 서버(api.도메인)를 가리키면 그 JS의 상대 API 경로도 그 서버의 후보로 넣는다
        (apiBase + "/api/v1/users" 같은 코드). 링크는 한 단계만 본다.
        """
        hosts = {a.host: a for a in assets}
        routes: dict[str, dict[str, None]] = {}

        def add(host: str, path: str) -> None:
            path = path.split("#", 1)[0].split("?", 1)[0]
            if not path.startswith("/") or path.startswith("//") or len(path) > 200:
                return
            routes.setdefault(host, {})[path] = None

        async def collect(a: Asset) -> None:
            home = await http.get_cached(f"https://{a.host}/")
            texts: list[str] = []
            if home is not None and home.status == 200:
                texts.append(home.text)
                texts += [js.text for js in await self._scripts(http, a.host, home)]
                for link in _LINK_ATTR.findall(home.text):
                    if link.startswith("/") and not link.startswith("//"):
                        add(a.host, link)
                    elif link.startswith(f"https://{a.host}/"):
                        add(a.host, link[len(f"https://{a.host}"):])
            robots = await http.get_cached(f"https://{a.host}/robots.txt")
            if robots is not None and robots.status == 200 and not _is_html(robots):
                for p in _ROBOTS_PATH.findall(robots.text):
                    add(a.host, p.replace("*", "").rstrip("$"))
            sitemap = await http.get_cached(f"https://{a.host}/sitemap.xml")
            if sitemap is not None and sitemap.status == 200:
                for loc in _SITEMAP_LOC.findall(sitemap.text)[:50]:
                    if loc.startswith("/"):
                        add(a.host, loc)
                    elif loc.startswith(f"https://{a.host}/"):
                        add(a.host, loc[len(f"https://{a.host}"):])
            for text in texts:
                api_hosts = {h for h in self._hosts_in(text, domain) if h in hosts and hosts[h].role == "api"}
                for m in _API_LITERAL.finditer(text):
                    for h in {a.host} | api_hosts:
                        add(h, m.group(1))
                for m in _API_URL.finditer(text):
                    h = m.group(1).lower()
                    if h in hosts:
                        add(h, m.group(2))

        # 호스트별 속도 제한은 호스트마다 따로라, 서로 다른 호스트는 동시에 모은다
        targets = [a for a in assets if a.role in ROUTE_ROLES
                   and not (a.role == "web" and a.host != primary_host and a.host in (domain, f"www.{domain}"))]
        await asyncio.gather(*(collect(a) for a in targets))
        return {h: list(v) for h, v in routes.items()}

    async def _ct_names(self, http, domain: str) -> list[str]:
        """#5 공개 인증서 발급 기록(crt.sh)에 적힌 하위 도메인 이름. 예약 도메인·조회 실패면 빈 목록."""
        if domain.endswith(_RESERVED_TLDS) or "." not in domain:
            return []
        r = await http.get(CT_LOG_URL.format(domain=domain), timeout=CT_TIMEOUT)
        if r is None or r.status != 200:
            log.info("인증서 발급 기록 조회 실패(%s), #5 없이 진행", r.status if r else "연결 실패")
            return []
        names: dict[str, None] = {}
        for raw in _CT_NAME.findall(r.text):  # 응답이 잘려도 읽히게 JSON 전체를 파싱하지 않는다
            for name in raw.replace("\\n", "\n").split("\n"):
                name = name.strip().lower().lstrip("*.")
                if name.endswith("." + domain) and re.fullmatch(r"[a-z0-9.\-]+", name):
                    names[name] = None
        return list(names)[:CT_NAME_LIMIT]

    # ================================================================ #34 백엔드 대행 서비스

    async def _check_baas(self, ctx, http, a: Asset) -> None:
        conf = a.baas or {}
        if conf.get("kind") == "supabase":
            await self._check_supabase(ctx, http, a, conf)
        elif conf.get("kind") == "firebase":
            await self._check_firebase(ctx, http, a, conf)

    async def _check_supabase(self, ctx, http, a: Asset, conf: dict) -> None:
        """화면 코드의 공개(anon) 키로 테이블을 읽을 수 있는지(RLS 꺼짐). 테이블당 1행만, 읽기만 한다."""
        key = conf.get("key")
        if not key:
            return
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        base = f"https://{a.host}/rest/v1"
        tables: list[str] = []
        root = await http.get(f"{base}/", extra_headers=headers)
        if root is not None and root.status == 200:
            try:
                import json
                spec = json.loads(root.text)
                tables = [p.strip("/") for p in (spec.get("paths") or {})
                          if p.startswith("/") and p.strip("/") and "/" not in p.strip("/")
                          and not p.startswith("/rpc")]
            except (ValueError, AttributeError):
                tables = []
        if not tables:
            tables = list(_COMMON_TABLES)
        tables.sort(key=lambda t: 0 if _PII_TABLE.search(t) else 1)
        open_tables: list[str] = []
        pii: tuple[str, list[str], Fetched] | None = None
        first: Fetched | None = None
        for t in tables[:SUPABASE_TABLE_LIMIT]:
            if not re.fullmatch(r"[A-Za-z0-9_]+", t):
                continue
            r = await http.get(f"{base}/{t}?select=*&limit=1", extra_headers=headers)
            if r is None or r.status != 200 or r.text.strip() in ("", "[]"):
                continue
            open_tables.append(t)
            first = first or r
            kinds, _ = _pii_shape(r)
            if kinds and pii is None:
                pii = (t, kinds, r)
        if not open_tables:
            return
        names = ", ".join(open_tables[:4])
        if pii is not None:
            t, kinds, r = pii
            self._add(ctx, a, 34, "pii", f"GET {base}/{t}?limit=1",
                      _clip(f"공개 키로 테이블 {len(open_tables)}개 읽힘({names}). {t}에 {'·'.join(kinds)} 형식(가림)"))
        else:
            self._add(ctx, a, 34, "data", f"GET {first.url if first else base}",
                      _clip(f"공개 키로 테이블 {len(open_tables)}개 읽힘({names}), 개인정보 형태는 아님"))

    async def _check_firebase(self, ctx, http, a: Asset, conf: dict) -> None:
        """Firebase 공개 읽기: Realtime DB(항목 이름만), Firestore(흔한 컬렉션 1건), Storage(파일 목록, #14)."""
        reported = False
        for db in conf.get("databases", [])[:2]:
            r = await http.get(f"{db}/.json?shallow=true")
            if r is not None and r.status == 200 and r.text.strip() not in ("null", "") and not _is_html(r):
                try:
                    import json
                    keys = list(json.loads(r.text) or {})
                except (ValueError, TypeError):
                    keys = []
                if keys:
                    self._add(ctx, a, 34, "firebase", f"GET {db}/.json?shallow=true",
                              f"Realtime Database 공개 읽기, 최상위 항목 {len(keys)}개(이름 가림)")
                    reported = True
                    break
        pid = conf.get("project")
        if pid and not reported:
            for col in _COMMON_TABLES[:FIRESTORE_COLLECTION_LIMIT]:
                url = (f"https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)"
                       f"/documents/{col}?pageSize=1")
                r = await http.get(url)
                if r is None or r.status != 200 or '"documents"' not in r.text:
                    continue
                kinds = _firestore_pii(r.text)
                situation = "pii" if kinds else "data"
                detail = f", {'·'.join(kinds)} 형식(가림)" if kinds else ", 개인정보 형태는 아님"
                self._add(ctx, a, 34, situation, f"GET {url}",
                          _clip(f"Firestore {col} 컬렉션 공개 읽기{detail}"))
                break
        for bucket in conf.get("buckets", [])[:2]:
            url = f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o?maxResults=20"
            r = await http.get(url)
            if r is not None and r.status == 200 and '"items"' in r.text:
                situation = "sensitive" if SENSITIVE_NAME.search(r.text) else "listing"
                self._add(ctx, a, 14, situation, f"GET {url}", "Firebase Storage 파일 목록 공개(파일 이름 가림)")
                break

    # ---------------------------------------------------------------- #21
    async def _check_cors(self, ctx, http, a: Asset) -> None:
        evil = "https://a2d-cors-probe.example"
        r = await http.get(f"https://{a.host}/api/v1/status", extra_headers={"Origin": evil})
        if r is None:
            return
        allow = (r.header("access-control-allow-origin") or "").strip()
        creds = (r.header("access-control-allow-credentials") or "").lower() == "true"
        if allow in (evil, "null") and creds:
            self._add(ctx, a, 21, "any_origin", f"GET {r.url}",
                      "아무 Origin을 그대로 허용하며 자격 증명도 허용")

    # ---------------------------------------------------------------- #31
    async def _check_cookie(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"https://{a.host}/")
        if r is None:
            return
        # 쿠키마다 따로 본다. 한 쿠키의 Secure가 다른 쿠키의 누락을 가리지 않게 한다.
        weak = []  # (로그인 쿠키인가, 이름, 빠진 속성)
        for cookie in r.set_cookies:
            name, attrs = _cookie_attrs(cookie)
            missing = [x for x in ("secure", "httponly", "samesite") if x not in attrs]
            if missing:
                weak.append((_is_session_cookie(name), name, missing))
        if not weak:
            return
        session, name, missing = max(weak, key=lambda w: (w[0], len(w[2])))  # 로그인 쿠키를 먼저 알린다
        more = f" 외 {len(weak) - 1}개" if len(weak) > 1 else ""
        self._add(ctx, a, 31, "login" if session else "other", f"GET {r.url}",
                  f"쿠키 {name[:40]}{more}에 {'·'.join(missing)} 속성 누락")

    # ---------------------------------------------------------------- #14
    async def _check_bucket(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"https://{a.host}/")
        if r is None or r.status != 200:
            return
        if "listbucketresult" in r.text.lower():
            situation = "sensitive" if SENSITIVE_NAME.search(r.text) else "listing"
            self._add(ctx, a, 14, situation, f"GET {r.url}",
                      "클라우드 저장소 파일 목록 공개(파일 이름 가림)")

    # ---------------------------------------------------------------- #6
    async def _check_dangling(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"https://{a.host}/")
        if r is None:
            return
        low = r.text.lower()
        if ("there isn't a github pages site here" in low or "no such app" in low
                or "nosuchbucket" in low):
            self._add(ctx, a, 6, "dangling", a.host, "해지된 외부 서비스 안내문 확인")

    # ---------------------------------------------------------------- #23 #25 #30 #27 #28
    async def _check_server_wide(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"https://{a.host}/")
        if r is not None:
            self._check_version(ctx, a, r)   # #23 #25
            self._check_headers(ctx, a, r)   # #30
        await self._check_redirect(ctx, http, a)  # #27
        await self._check_tls(ctx, a)              # #28

    def _check_version(self, ctx, a: Asset, r: Fetched) -> None:
        server = r.header("server") or ""
        powered = r.header("x-powered-by") or ""
        for product, version in _versions(server + " " + powered):
            vulns = KNOWN_VULNS.get((product, version))
            if vulns:
                situation = _vuln_situation(vulns)
                cve_text = ", ".join(f"{v['id']}({'KEV' if v.get('kev') else 'CVSS ' + str(v['cvss'])})"
                                     for v in vulns)
                self._add(ctx, a, 23, situation, f"GET {r.url}",
                          f"서버 버전 {product} {version}, 알려진 약점 {cve_text}", cves=vulns)
            major_minor = ".".join(version.split(".")[:2])
            if (product, major_minor) in EOL:
                self._add(ctx, a, 25, "server", f"GET {r.url}",
                          f"{product} {version}은 지원이 끝난 버전")

    def _check_headers(self, ctx, a: Asset, r: Fetched) -> None:
        missing = [h for h in SECURITY_HEADERS if r.header(h) is None]
        if missing:
            self._add(ctx, a, 30, "basic", f"GET {r.url}", f"보안 헤더 누락: {', '.join(missing)}")

    async def _check_redirect(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"http://{a.host}/")
        if r is None:
            return
        redirected = r.status in (301, 302, 307, 308) and (r.location or "").startswith("https://")
        if not redirected and r.status == 200:
            self._add(ctx, a, 27, "basic", f"GET http://{a.host}/", "HTTP 접속을 HTTPS로 옮기지 않음")

    async def _check_tls(self, ctx, a: Asset) -> None:
        # 자산 찾기에서 본 인증서를 쓴다. 없을 때만 다시 연결한다(TLS 핸드셰이크는 블로킹)
        info = a.cert if a.cert is not None else await asyncio.to_thread(self._tls.inspect, a.host)
        if info.error or info.not_after is None:
            return
        days = (info.not_after - dt.datetime.now(dt.timezone.utc)).days
        if days < 0:
            situation = "expired"
            ev = "인증서가 이미 만료됨"
        elif days <= 14:
            situation = "expiring14"
            ev = f"인증서가 {days}일 뒤 만료"
        elif days <= 30:
            situation = "expiring30"
            ev = f"인증서가 {days}일 뒤 만료"
        elif info.self_signed or not info.hostname_ok or info.trusted is False:
            situation = "invalid"
            ev = "자체 서명이거나 이름이 맞지 않거나 믿을 수 없는 기관이 발급한 인증서"
        else:
            return
        self._add(ctx, a, 28, situation, f"TLS https://{a.host}", ev)

    # ---------------------------------------------------------------- #32
    async def _check_mail(self, ctx: EngineContext) -> None:
        domain = ctx.domain.lower().strip(".")
        try:
            spf = _find_txt(await asyncio.to_thread(self._dns.txt, domain), "v=spf1")
            dmarc = _find_txt(await asyncio.to_thread(self._dns.txt, f"_dmarc.{domain}"), "v=dmarc1")
        except DnsUnavailable as e:
            log.info("DNS 무응답, #32는 판정하지 않음: %s", e)  # 모르는 것을 '없음'으로 보고하지 않는다
            return
        spf_enforces = spf is not None and ("-all" in spf or "~all" in spf)
        dmarc_enforces = dmarc is not None and ("p=quarantine" in dmarc.lower() or "p=reject" in dmarc.lower())
        if dmarc_enforces and not spf_enforces:
            situation, ev = "weak_spf", "DMARC는 사칭을 막지만 SPF가 없거나 느슨함"
        elif spf_enforces and not dmarc_enforces:
            situation, ev = "weak_dmarc", "SPF는 있으나 DMARC가 없거나 p=none"
        elif not spf_enforces and not dmarc_enforces:
            situation, ev = "none", "SPF·DMARC가 사칭을 막지 못함"
        else:
            return
        # 도메인 자체 발견: 꼭짓점 자산(web)에 붙인다
        host = f"www.{domain}"
        self._add_host(ctx, host, 32, situation, f"DNS {domain}", ev) or \
            self._add_host(ctx, domain, 32, situation, f"DNS {domain}", ev)

    # ---------------------------------------------------------------- 공용
    def _add(self, ctx: EngineContext, a: Asset, check_id: int, situation: str,
             location: str, evidence: str, *, cves: list[dict] | None = None) -> None:
        try:
            ctx.add_finding(RawFinding(host=a.host, check_id=check_id, situation=situation,
                                       location=location, evidence=_clip(evidence), cves=cves or []))
        except ValueError:
            log.exception("발견 기록 실패 #%s/%s", check_id, situation)

    def _add_host(self, ctx: EngineContext, host: str, check_id: int, situation: str,
                  location: str, evidence: str) -> bool:
        try:
            ctx.add_finding(RawFinding(host=host, check_id=check_id, situation=situation,
                                       location=location, evidence=_clip(evidence)))
            return True
        except ValueError:
            return False


# ==================================================================== 보조 함수

def _identify_components(home: Fetched) -> list[dict]:
    """#24 홈페이지 부품 식별. 이미 받은 첫 화면(본문·헤더)만 읽는다. 점수에는 넣지 않고 자산 정보에 표시한다."""
    comps: list[dict] = []

    def add(name: str, version: str, eol: bool = False) -> None:
        if all(c["name"].lower() != name.lower() for c in comps):
            comps.append({"name": name, "version": version, "eol": eol})

    m = _GENERATOR.search(home.text)
    if m:
        gen = m.group(1).strip()
        gv = _GENERATOR_VERSION.match(gen)
        add(*(gv.groups() if gv else (gen, "")))
    jm = _JQUERY.search(home.text)
    if jm:
        add("jQuery", jm.group(1), eol=int(jm.group(1).split(".")[0]) < 3)  # 1.x·2.x는 지원 종료
    server = f"{home.header('server') or ''} {home.header('x-powered-by') or ''}"
    for product, version in _versions(server):
        major_minor = ".".join(version.split(".")[:2])
        add(_PRODUCT_NAMES.get(product, product), version, eol=(product, major_minor) in EOL)
    low = home.text.lower()
    for name, marks in _FRAMEWORK_MARKS:
        if any(mark in low for mark in marks):
            add(name, "")
    return comps


def _tls_label(version: str | None) -> str | None:
    """ssl의 'TLSv1.3'을 API 명세의 'TLS 1.3' 표기로 바꾼다."""
    if not version:
        return None
    return re.sub(r"^TLSv?(\d)", r"TLS \1", version)


def _token() -> str:
    import secrets
    return secrets.token_hex(4)


def _abs(src: str) -> str:
    return src if src.startswith("/") else "/" + src


def _looks_like_file(r: Fetched) -> bool:
    """내려받기용 파일 응답인지(#8). HTML(모르는 경로를 index로 돌려주는 SPA)은 파일로 보지 않는다."""
    ct = r.header("content-type") or ""
    if "html" in ct:
        return False
    if "zip" in ct or "sql" in ct or "octet-stream" in ct or "x-gzip" in ct or "gzip" in ct:
        return True
    head = r.text[:64].lstrip().upper()
    magic = ("PK\x03\x04", "SQLITE", "-- ", "/*", "INSERT INTO", "CREATE TABLE", "DROP TABLE")
    return r.text[:8].startswith("PK\x03\x04") or any(head.startswith(m.upper()) for m in magic)


def _is_html(r: Fetched) -> bool:
    if "html" in (r.header("content-type") or ""):
        return True
    head = r.text[:256].lstrip().lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


def _same_as(r: Fetched, catch_all: Fetched | None) -> bool:
    """없는 주소의 200 응답과 같은 내용인지. 모르는 경로를 모두 index.html로 돌려주는 SPA를 걸러 낸다.

    주소가 본문에 찍히는 서버가 있어 각자의 경로를 지우고 비교한다.
    """
    if catch_all is None or r.status != catch_all.status:
        return False

    def body(x: Fetched) -> str:
        return x.text.replace(_url_path(x.url), "").strip()

    return body(r) == body(catch_all)


def _url_path(url: str) -> str:
    rest = url.split("://", 1)[-1]
    return "/" + rest.split("/", 1)[1] if "/" in rest else "/"


_ENV_LINE = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*=")
_GIT_HEAD = re.compile(r"\s*(?:ref:[ \t]*refs/|[0-9a-f]{40}\b)")


def _config_file_matches(path: str, r: Fetched) -> bool:
    """설정 파일·저장소 파일의 실제 형식인지(#9). HTML이나 아무 텍스트로는 켜지 않는다."""
    if _is_html(r):
        return False
    if path == "/.env":
        return bool(_ENV_LINE.search(r.text))
    if path == "/.git/HEAD":
        return bool(_GIT_HEAD.match(r.text))
    if path == "/.git/config":
        return "[core]" in r.text
    if path.startswith("/.env"):
        return bool(_ENV_LINE.search(r.text))
    low = r.text.lower()
    if path.endswith("sftp.json") or path == "/sftp-config.json":
        return '"host"' in low and ('"password"' in low or '"username"' in low or '"user"' in low)
    if path.endswith((".php.bak", ".php~")):
        return "<?php" in low and ("password" in low or "db_" in low or "mysql" in low)
    if path == "/docker-compose.yml":
        return "services:" in low and ("password" in low or "secret" in low or "environment:" in low)
    if path in ("/application.yml", "/application.properties"):
        return ("datasource" in low or "spring." in low) and ("password" in low or "secret" in low)
    if path == "/appsettings.json":
        return "connectionstrings" in low
    return False


def _status_page_matches(path: str, r: Fetched) -> bool:
    """운영·상태 페이지의 실제 내용인지(#20). 경로만 열려 있다고 켜지 않는다."""
    import json

    low = r.text.lower()
    if path == "/actuator/env":
        try:
            obj = json.loads(r.text)
        except ValueError:
            return False
        return isinstance(obj, dict) and bool({"propertySources", "activeProfiles"} & set(obj))
    if path == "/server-status":
        return "server status" in low or "total accesses" in low
    if path == "/phpinfo.php":
        return "phpinfo()" in low or "php version" in low
    if path == "/metrics":
        return not _is_html(r) and ("# help " in low or "# type " in low)
    if path in ("/info.php", "/test.php"):
        return "phpinfo()" in low or ("php version" in low and "configuration" in low)
    if path == "/_ignition/health-check":
        return '"can_execute_commands"' in low
    if path == "/telescope/requests":
        return "telescope" in low and not _same_as_login(low)
    if path == "/debug/vars":
        return not _is_html(r) and ('"cmdline"' in low or '"memstats"' in low)
    return False


def _same_as_login(low: str) -> bool:
    return 'type="password"' in low


def _is_api_doc(r: Fetched) -> bool:
    """실제 API 설명서인지(#17). 일반 /docs 페이지가 걸리지 않게 OpenAPI JSON이나 UI 표식을 본다."""
    import json

    if "json" in (r.header("content-type") or ""):
        try:
            obj = json.loads(r.text)
        except ValueError:
            return False
        return isinstance(obj, dict) and bool({"openapi", "swagger", "paths"} & set(obj))
    low = r.text.lower()
    return "swagger-ui" in low or "redoc" in low or "swagger.json" in low or "openapi.json" in low


def _is_login(text: str) -> bool:
    low = text.lower()
    return ('type="password"' in low or "type='password'" in low
            or ("관리자" in text and ("로그인" in text or "콘솔" in text)))


def _cookie_attrs(cookie: str) -> tuple[str, set[str]]:
    """Set-Cookie 한 줄을 (이름, 소문자 속성 이름 집합)으로 나눈다. 값 안의 글자는 속성으로 보지 않는다."""
    first, *rest = cookie.split(";")
    name = first.split("=", 1)[0].strip()
    return name, {part.split("=", 1)[0].strip().lower() for part in rest if part.strip()}


def _is_session_cookie(name: str) -> bool:
    low = name.lower()
    return any(k in low for k in ("session", "sess", "sid", "auth", "token", "jwt", "login"))


def _secret_kinds(text: str) -> list[str]:
    """비밀키 형태를 센다. 공개용 키(pk_live_·AIza·Supabase anon 등)와 문서용 예시 키는 세지 않는다."""
    kinds = [name for name, pat in SECRET_PATTERNS.items()
             if any(not _PLACEHOLDER.search(m.group(0)) for m in pat.finditer(text))]
    if any(_jwt_role(m.group(1)) == "service_role" for m in _JWT.finditer(text)):
        kinds.append("Supabase service_role 키")
    for m in _DB_URL.finditer(text):
        password, host = m.group(2).lower(), m.group(3).lower()
        if (host in _DB_URL_DUMMY_HOSTS or password in _DB_URL_DUMMY_PASS or password.startswith("$")
                or password.startswith(("{", "<")) or _PLACEHOLDER.search(m.group(0))):
            continue
        kinds.append("DB 접속 주소(비밀번호 포함)")
        break
    return kinds


def _jwt_payload(payload_b64: str) -> dict | None:
    import base64
    import json

    try:
        raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _jwt_role(payload_b64: str) -> str | None:
    role = (_jwt_payload(payload_b64) or {}).get("role")
    return role if isinstance(role, str) else None


def _collect_baas(text: str, out: dict[str, dict]) -> None:
    """화면 코드에서 Supabase 프로젝트와 공개 키, Firebase 설정을 모은다(#34). 키 값은 점검에만 쓰고 저장하지 않는다."""
    anon_by_ref: dict[str, str] = {}
    loose_anon: list[str] = []
    for m in _JWT.finditer(text):
        p = _jwt_payload(m.group(1)) or {}
        if p.get("role") == "anon":
            if isinstance(p.get("ref"), str):
                anon_by_ref[p["ref"].lower()] = m.group(0)
            else:
                loose_anon.append(m.group(0))
    publishable = _SB_PUBLISHABLE.findall(text)
    refs = {r.lower() for r in _SUPABASE_HOST.findall(text)}
    for ref in refs:
        host = f"{ref}.supabase.co"
        conf = out.setdefault(host, {"kind": "supabase", "alias": f"Supabase {ref[:6]}", "key": None})
        key = anon_by_ref.get(ref) or (publishable[0] if publishable else None) or \
            (loose_anon[0] if loose_anon and len(refs) == 1 else None)
        conf["key"] = conf["key"] or key
    projects = set(_FB_PROJECT.findall(text))
    dbs = [u.lower() for u in _FB_DB_URL.findall(text)]
    buckets = _FB_BUCKET.findall(text)
    if projects or dbs:
        pid = next(iter(sorted(projects)), None) or dbs[0].split("//", 1)[1].split(".")[0].replace("-default-rtdb", "")
        host = f"{pid}.firebaseapp.com"
        conf = out.setdefault(host, {"kind": "firebase", "alias": f"Firebase {pid}", "project": pid,
                                     "databases": [], "buckets": []})
        for d in dbs:
            if d not in conf["databases"]:
                conf["databases"].append(d)
        for b in buckets:
            if b not in conf["buckets"]:
                conf["buckets"].append(b)


def _openapi_get_paths(r: Fetched) -> list[str]:
    """API 설명서(OpenAPI·Swagger)에서 변수 없는 GET 경로를 뽑는다(#16 후보)."""
    import json

    try:
        spec = json.loads(r.text)
    except ValueError:
        return []
    paths = spec.get("paths") if isinstance(spec, dict) else None
    if not isinstance(paths, dict):
        return []
    base = ""
    if isinstance(spec.get("basePath"), str):
        base = spec["basePath"].rstrip("/")
    out = []
    for p, ops in paths.items():
        if isinstance(p, str) and "{" not in p and isinstance(ops, dict) and "get" in ops:
            out.append(base + p)
    return out


def _probe_worthy(path: str) -> bool:
    """#16으로 불러 볼 만한 경로인지. 정적 파일·상태를 바꿀 수 있는 이름·루트는 뺀다."""
    return (path not in ("/", "") and not _STATIC_EXT.search(path) and not _UNSAFE_ROUTE.search(path)
            and not BACKUP_EXT.search(path))


def _firestore_pii(text: str) -> list[str]:
    """Firestore 문서 응답(fields 안에 값이 들어 있는 형태)에서 개인정보 형태를 본다."""
    import json

    try:
        docs = json.loads(text).get("documents") or []
    except (ValueError, AttributeError):
        return []
    keys = {str(k).lower() for d in docs[:5] if isinstance(d, dict) for k in (d.get("fields") or {})}
    kinds = []
    if _EMAIL.search(text):
        kinds.append("이메일")
    if _PHONE.search(text):
        kinds.append("전화번호")
    if keys & _PII_KEYS:
        kinds.append("개인정보 필드")
    return kinds if (keys & _PII_KEYS or len(kinds) >= 2) else []


def _sourcemap_url(js_text: str, js_url: str) -> str | None:
    """코드 끝의 sourceMappingURL 주석이 가리키는 주소. 코드에 들어 있는 소스맵(data:)은 None."""
    from urllib.parse import urljoin

    found = _SOURCEMAP_URL.findall(js_text)
    if not found or found[-1].startswith("data:"):
        return None
    return urljoin(js_url, found[-1])


def _is_sourcemap(r: Fetched) -> bool:
    import json

    if _is_html(r):
        return False
    try:
        obj = json.loads(r.text)
    except ValueError:
        return False
    return isinstance(obj, dict) and bool({"mappings", "sources", "sourcesContent"} & set(obj))


def _pii_shape(r: Fetched) -> tuple[list[str], int | None]:
    """응답이 개인정보 형태인지(#16). JSON 응답만 본다. HTML(푸터 메일 등)은 API 응답으로 보지 않는다.

    오탐이 가장 비싼 항목(확인됨·C=5 → 100)이라, 개인정보 필드가 있거나 값 형태가 2종 이상일 때만
    pii로 본다. 값 하나(예: 안내용 메일 하나)로는 켜지 않는다.
    """
    import json

    if "json" not in (r.header("content-type") or ""):
        return [], None
    try:
        obj = json.loads(r.text)
    except ValueError:
        return [], None
    body = r.text
    value_kinds: list[str] = []
    if _EMAIL.search(body):
        value_kinds.append("이메일")
    if _PHONE.search(body):
        value_kinds.append("전화번호")
    items = _items_of(obj)
    count = len(items) if items is not None else None
    has_field = False
    if items is not None:
        keys = {str(k).lower() for it in items[:5] if isinstance(it, dict) for k in it}
        has_field = bool(keys & _PII_KEYS)
    # 강한 근거: 개인정보 필드가 있거나, 값 형태가 2종 이상
    if not (has_field or len(value_kinds) >= 2):
        return [], count
    kinds = value_kinds + (["개인정보 필드"] if has_field else [])
    return kinds, count


def _items_of(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("items", "data", "results", "list"):
            if isinstance(obj.get(key), list):
                return obj[key]
        return [obj]
    return None


def _versions(text: str) -> list[tuple[str, str]]:
    out = []
    for name, ver in re.findall(r"([A-Za-z][A-Za-z0-9+]+)[/ ](\d+\.\d+(?:\.\d+)?)", text):
        out.append((name.lower(), ver))
    return out


def _vuln_situation(vulns: list[dict]) -> str:
    if any(v.get("kev") for v in vulns):
        return "kev"
    top = max((v.get("cvss") or 0) for v in vulns)
    if top >= 9.0:
        return "cvss9"
    if top >= 7.0:
        return "cvss7"
    return "cvss_low"


def _find_txt(records: list[str], prefix: str) -> str | None:
    for r in records:
        if r.lower().startswith(prefix.lower()):
            return r
    return None
