"""실제 대상을 읽기만 해서 점검하는 엔진(FR-02·FR-03, 상세설계 4절 "점검 1회의 실행 순서").

1. 자산 찾기: 하위 도메인 단어 목록(#1), 공개 인증서 발급 기록(#5, crt.sh. 예약 도메인은 묻지 않는다),
   크롤링(#2·#3, engine.crawl)으로 우리 서버마다 내부 링크를 끝까지 따라가며 처음 보는 우리 호스트를 더한다.
   화면·JS에 적힌 클라우드 저장소(#14)와 Supabase·Firebase 프로젝트(#34)도 자산으로 등록한다.
2. 점검: 크롤링으로 연 모든 페이지·JS에서 #10 #11 #12 #13 #16 #18을 보고, 자산 역할별 점검(#8 #9 #17 #19
   #20 #21 #31)과 서버 공통 점검(#23 #25 #27 #28 #30), 메일·도메인(#32)을 돈다.

대상에는 읽기(GET·DNS·TLS) 요청만 보내고, logout·delete처럼 상태를 바꿀 수 있는 이름의 경로는 열지 않는다.
요청 수 상한은 기본으로 두지 않고(A2D_REQUEST_LIMIT=0), 같은 페이지·같은 틀의 페이지만 건너뛴다.
호스트당 초당 2건과 점검 제한 시간(A2D_TIME_LIMIT_SEC)은 지킨다. 발견은 ctx.add_finding으로, 증거는 마스킹된 발췌만 넘긴다.
연결 통로(HTTP·DNS·TLS)는 engine.net의 구현을 쓰고, 테스트는 같은 자리에 가짜를 끼운다.
#7·#15·#22·#29는 2차다.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from dataclasses import dataclass, field

from ..config import Settings
from .base import Engine, EngineContext, EngineError, RawAsset, RawFinding
from . import intel
from .crawl import UNSAFE_ROUTE, Crawler, HostMap
from .net import (CertInfo, Dns, DnsResolver, DnsUnavailable, Fetched, HttpClient, Tls, TlsInspector,
                  open_http_client)

log = logging.getLogger("a2d.engine.live")

# 자산 찾기에 쓰는 흔한 하위 도메인 이름(#1). 대상 DNS가 응답하는 것만 자산이 된다.
SUBDOMAIN_WORDS = ("www", "api", "admin", "staging", "stage", "stg", "dev", "test", "qa", "beta", "demo",
                   "mail", "webmail", "m", "mobile", "app", "apps", "portal", "cms", "blog", "shop", "store",
                   "static", "cdn", "img", "images", "assets", "files", "upload", "media", "docs", "help",
                   "support", "status", "auth", "login", "sso", "id", "account", "my", "dashboard", "console",
                   "manage", "manager", "backoffice", "internal", "intranet", "vpn", "remote", "git", "gitlab",
                   "jenkins", "ci", "grafana", "kibana", "monitor", "old", "new", "legacy", "v1", "v2",
                   "partner", "partners", "event", "events", "promo", "recruit", "careers", "jobs")

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
# 크롤링(경로 찾기)을 하는 우리 서버 자산. 외부 위탁·클라우드·BaaS는 따라가지 않는다
CRAWL_ROLES = ("web", "api", "admin", "dev")
# API 서버는 링크가 없는 경우가 많아, 흔한 REST 자원 이름을 크롤링 시작점에 더한다(일반 API 점검 도구와 같은 방식)
COMMON_API_PATHS = tuple(f"{prefix}/{res}" for prefix in ("/api", "/api/v1", "/v1")
                         for res in ("users", "members", "customers", "accounts", "profiles", "orders"))
_API_PREFIX = re.compile(r"^/(?:api|v\d+|rest|graphql)(?:/|$)", re.I)
SOURCEMAP_MAX_BYTES = 16 * 1024 * 1024
_ADMIN_PATH = re.compile(r"(?:^|/)(?:admin|adm|administrator|manager|backoffice|console|wp-admin|wp-login\.php"
                         r"|phpmyadmin|pma)(?:/|\.|$)", re.I)
_ADMIN_TITLE = re.compile(r"<title>[^<]*(?:admin|관리자|backoffice|console|관리 콘솔)", re.I)
CORS_PROBE_LIMIT = 3  # #21: 호스트마다 찾은 API 응답 중 몇 곳에 Origin을 바꿔 보는지

# 외부 서비스의 '해지됨' 안내문(#6 하위 도메인 탈취 후보). can-i-take-over-xyz에 정리된 서비스 중
# 국내에서 자주 쓰는 것. CNAME이 이 서비스를 가리키고 안내문이 보이면 남이 그 이름을 가져갈 수 있다.
TAKEOVER_SIGNS = (
    (("github.io",), "there isn't a github pages site here"),
    (("herokuapp.com", "herokudns.com"), "no such app"),
    (("amazonaws.com",), "nosuchbucket"),
    (("myshopify.com",), "sorry, this shop is currently unavailable"),
    (("azurewebsites.net", "cloudapp.net", "trafficmanager.net", "azureedge.net"), "404 web site not found"),
    (("bitbucket.io",), "repository not found"),
    (("ghost.io",), "the thing you were looking for is no longer here"),
    (("surge.sh",), "project not found"),
    (("readthedocs.io",), "unknown to read the docs"),
    (("pantheonsite.io",), "the gods are wise"),
    (("zendesk.com",), "help center closed"),
    (("wordpress.com",), "do you want to register"),
    (("netlify.app", "netlify.com"), "not found - request id"),
    (("tilda.ws",), "please renew your subscription"),
)
# 개발 모드·디버그 화면 표시(#19). 프레임워크가 개발 모드에서만 내보내는 문구다
DEBUG_MARKS = ("debug=true", "you're seeing this error because you have debug = true", "werkzeug debugger",
               "whoops! there was an error", "ignition-", "phpdebugbar", "sf-toolbar", "symfony profiler",
               "/_next/static/development/", "webpack-hmr", "/@vite/client", "react-refresh",
               "action controller: exception caught", "laravel debugbar")

# BaaS(#34). 설정 값은 우리 화면 코드에 적힌 것만 쓴다(프로젝트 이름을 추측하지 않는다)
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
# 버전은 몰라도 쓰는 것만은 알 수 있는 컴포넌트(#24 식별 범위: 기존 방식 + 바이브코딩 방식)
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

CVE_ATTACH_LIMIT = 10  # #23 발견에 붙여 넘길 CVE 수(점수가 높은 순). 전체 건수는 증거 문장에 적는다

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
    cname: str | None = None  # #6 외부 서비스를 가리키는 CNAME
    reported: set[int] = field(default_factory=set)  # 이 점검에서 이미 보고한 항목 번호


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
            ctx.set_stage("discovering", "자산과 페이지를 찾는 중", 0, 1)
            assets, site = await self._discover(ctx, http)
            if not assets:
                raise EngineError("이 도메인에서 주소가 있는 호스트를 찾지 못해 점검하지 못했습니다. "
                                  "도메인의 DNS 레코드를 확인해 주세요.")
            await self._ensure_reachable(http, assets)
            ctx.set_stage("discovering", "자산과 페이지를 찾는 중", 1, 1)

            # 같은 서비스를 가리키는 루트·www 자산에 점검이 겹치지 않게, 대표 웹 자산 하나만 깊게 본다.
            domain = ctx.domain.lower().strip(".")
            primary_host = self._primary_host(assets, domain)

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
                found = await self._check_asset(ctx, http, a, primary_host=primary_host,
                                                hm=site.maps.get(a.host),
                                                run_server_wide=a.host == server_wide_host,
                                                admin_login_found=admin_login_found)
                admin_login_found = admin_login_found or found
                done += 1
                ctx.set_stage("checking", "노출을 점검하는 중", done, total + 1)
            await self._check_mail(ctx)  # #32 (DNS)
            await self._check_domain_expiry(ctx, http)  # #33 (RDAP)
            ctx.set_stage("checking", "노출을 점검하는 중", total + 1, total + 1)
        finally:
            if self._owns_client:
                await client.aclose()

    @staticmethod
    def _primary_host(assets: list[Asset], domain: str) -> str | None:
        web_assets = [a for a in assets if a.role == "web" and a.host in (domain, f"www.{domain}")]
        web_assets = web_assets or [a for a in assets if a.role == "web"]
        primary = next((a for a in web_assets if a.host == f"www.{domain}"),
                       web_assets[0] if web_assets else None)
        return primary.host if primary else None

    # ================================================================ 자산 찾기

    async def _resolve_new(self, host: str, domain: str, found: dict[str, Asset], by: int) -> None:
        """처음 보는 우리 도메인 호스트를 DNS로 확인해 자산 후보에 넣는다."""
        if host in found:
            if by not in found[host].found_by:
                found[host].found_by.append(by)
            return
        if not (host == domain or host.endswith("." + domain)):
            return
        try:
            cname = await asyncio.to_thread(self._dns.cname, host)
            addrs = [] if cname else await asyncio.to_thread(self._dns.a, host)
        except DnsUnavailable as e:
            log.info("DNS 무응답, 건너뜀: %s", e)
            return
        if cname or addrs:
            found[host] = self._classify(host, domain, cname)
            found[host].found_by.append(by)

    async def _discover(self, ctx: EngineContext, http: HttpClient) -> tuple[list[Asset], Crawler]:
        domain = ctx.domain.lower().strip(".")
        found: dict[str, Asset] = {}

        # #1 하위 도메인 찾기 + 루트 도메인. DNS는 블로킹이라 스레드로 보내고, 사이사이 중지를 확인한다.
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

        # #5 인증서 발급 기록: 단어 목록에 없는 하위 도메인(api-prod, partner 등)을 공개 CT 로그에서 찾는다
        for host in await self._ct_names(http, domain):
            await self._resolve_new(host, domain, found, 5)

        # #2·#3 경로 찾기: 우리 서버마다 내부 링크를 끝까지 따라간다. 거기서 처음 보는 우리 호스트가 나오면
        # DNS로 확인해 자산에 넣고 그 호스트도 따라간다(더 나오지 않을 때까지).
        site = Crawler(http, domain, page_limit=self.s.crawl_page_limit)
        while True:
            primary = self._primary_host(list(found.values()), domain)
            targets = [h for h, a in sorted(found.items()) if a.role in CRAWL_ROLES and h not in site.maps
                       and not (h in (domain, f"www.{domain}") and primary and h != primary)]
            if not targets:
                break
            site.api_hosts |= {h for h, a in found.items() if a.role == "api"}
            await site.crawl(targets, {h: list(COMMON_API_PATHS) for h in targets if found[h].role == "api"})
            for host in sorted(site.new_hosts):
                await self._resolve_new(host, domain, found, 2)
            site.new_hosts.clear()
        for host, hm in site.maps.items():
            if host in found:
                if hm.pages and 2 not in found[host].found_by:
                    found[host].found_by.append(2)
                ctx.audit("system", "crawl", {"host": host},
                          f"페이지 {len(hm.pages)}개·JS {len(hm.scripts)}개 확인, 경로 {len(hm.routes)}개 찾음"
                          f"(같은 틀이라 건너뜀 {hm.skipped_same_template}, 상태를 바꿀 수 있어 안 엶 "
                          f"{hm.skipped_unsafe}, 페이지 상한으로 건너뜀 {hm.skipped_page_limit})")

        # 찾은 모든 화면·JS에 적힌 클라우드 저장소(#14)와 BaaS(#34). 이름을 추측하지 않는다
        cloud_hosts: set[str] = set()
        baas: dict[str, dict] = {}
        for hm in site.maps.values():
            for text in [r.text for _, r in hm.html_pages()] + [r.text for r in hm.scripts.values()]:
                cloud_hosts |= {m.group(1).lower() for m in _CLOUD_HOST.finditer(text)}
                _collect_baas(text, baas)
        primary = self._primary_host(list(found.values()), domain)
        if primary and primary in site.maps:
            home = site.maps[primary].pages.get("/")
            if home is not None and home.status == 200:
                found[primary].components = _identify_components(home)  # #24
                server = f"{home.header('server') or ''} {home.header('x-powered-by') or ''}"
                for product, version in _versions(server):
                    name = _PRODUCT_NAMES.get(product, product)
                    if await intel.end_of_life(http, product, version):
                        for c in found[primary].components:
                            if c["name"] == name and c["version"] == version:
                                c["eol"] = True
        for host in sorted(cloud_hosts):
            if host not in found:
                found[host] = Asset(host, host.split(".")[0], "cloud", 5,
                                    "우리 사이트가 쓰는 클라우드 저장소", found_by=[14], tags=["cloud"])
        for host, conf in sorted(baas.items()):
            if host not in found:
                found[host] = Asset(host, conf["alias"], "baas", 5,
                                    "우리 화면 코드가 쓰는 BaaS", found_by=[34], tags=["baas"],
                                    baas=conf)

        # 인증서·TLS 버전: 우리 서버 자산마다 한 번씩, 동시에 본다(자산 정보 표시와 #28이 함께 쓴다)
        ctx.budget.check()
        tls_assets = [a for a in found.values() if a.role in TLS_ROLES]
        certs = await asyncio.gather(*(asyncio.to_thread(self._tls.inspect, a.host) for a in tls_assets))
        for a, cert in zip(tls_assets, certs):
            a.cert = cert

        # 등록. 외부 위탁 서비스(#4)는 식별만 하고 자산 메모로 남긴다.
        assets = sorted(found.values(), key=lambda a: (self._role_order(a.role), a.host))
        for a in assets:
            tls_version = _tls_label(a.cert.tls_version) if a.cert and not a.cert.error else None
            ctx.add_asset(RawAsset(host=a.host, alias=a.alias, url=f"https://{a.host}/",
                                   found_by=sorted(set(a.found_by)), tags=a.tags,
                                   importance=a.importance, importance_rule=a.importance_rule,
                                   components=a.components, tls_version=tls_version))
        return assets, site

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
            if any(cname.rstrip(".").endswith(sfx) for sfxs, _ in TAKEOVER_SIGNS for sfx in sfxs):
                return Asset(host, label or host, "dangling", 3, "외부 서비스로 연결된 하위 도메인",
                             tags=["external"], cname=cname)
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
                           admin_login_found: bool = False, hm: HostMap | None = None) -> bool:
        """자산 하나를 점검한다. 관리자 로그인 화면(#18)을 찾았으면 True."""
        if a.role in ("external", "dangling"):
            await self._check_dangling(ctx, http, a)  # #6. 위탁 서비스 내용은 점검하지 않는다(#4 식별만)
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
        hm = hm or HostMap(a.host)

        if a.role == "web" and a.host == primary_host:  # 대표 웹 자산에서만(루트·www 중복 방지)
            # 없는 주소부터 본다. 그 응답(모르는 경로를 index로 돌려주는 SPA 등)을 아래 경로 점검이 걸러 쓴다.
            catch_all = await self._check_error_page(ctx, http, a)  # #11
            await self._check_files(ctx, http, a, catch_all, hm)    # #8 #9 #10
            await self._check_status_pages(ctx, http, a, catch_all)  # #20
            if not admin_login_found:  # 관리자 하위 도메인에서 이미 찾았으면 한 번만 센다
                admin_found = await self._check_admin_path(ctx, http, a, catch_all)  # #18 (www/admin 등)
            await self._check_cookie(ctx, http, a)      # #31
            await self._check_graphql(ctx, http, a)     # #17
        if a.role == "api":
            doc = await self._check_api_docs(ctx, http, a)  # #17
            await self._probe_api_doc(http, a, doc, hm)     # 설명서의 GET 경로도 #16 대상에 넣는다
            await self._check_graphql(ctx, http, a)     # #17
            await self._check_cors(ctx, http, a, hm)    # #21
        if a.role == "admin":
            admin_found = await self._check_admin_host(ctx, http, a)  # #18
        if a.role == "dev":
            await self._check_dev_server(ctx, http, a, hm)  # #19

        # 크롤링으로 연 모든 페이지·JS(모든 우리 서버 공통)
        await self._check_code(ctx, http, a, hm)        # #12 #13
        self._check_unauth_api(ctx, a, hm)              # #16
        if not (admin_found or admin_login_found):
            admin_found = self._check_crawled_admin(ctx, a, hm)  # #18
        self._check_crawled_pages(ctx, a, hm, primary=a.host == primary_host)  # #10 #11

        if run_server_wide and a.role in ("web", "api", "admin"):
            await self._check_server_wide(ctx, http, a)  # #23 #25 #30 #27 #28
        return admin_found

    # ---------------------------------------------------------------- #8 #9 #10
    async def _check_files(self, ctx, http, a: Asset, catch_all: Fetched | None = None,
                           hm: HostMap | None = None) -> None:
        # 흔한 백업 이름 + 도메인 이름을 딴 압축 파일 + 크롤링에서 찾은(robots·링크에 적힌) 압축·덤프 파일
        label = ctx.domain.lower().strip(".").split(".")[0]
        found_files = [p for p in (hm.routes if hm else {}) if BACKUP_EXT.search(p)]
        backup_paths = list(dict.fromkeys([*BACKUP_PATHS, f"/{label}.zip", f"/{label}.sql", *found_files]))
        for path in backup_paths:
            r = await http.get_cached(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and _looks_like_file(r) and not _same_as(r, catch_all):
                self._add(ctx, a, 8, "confirmed", f"GET {r.url}",
                          _clip(f"{path} 200 응답, 파일 형식 확인(마스킹)"))
                break  # 자산당 한 건
        reported: set[str] = set()
        for path, situation in CONFIG_PATHS:
            if situation in reported:
                continue  # 같은 저장소(.git)는 한 건으로 센다
            r = await http.get(f"https://{a.host}{path}")
            if (r is not None and r.status == 200 and not _same_as(r, catch_all)
                    and _config_file_matches(path, r)):
                self._add(ctx, a, 9, situation, f"GET {r.url}", f"{path} 200 응답, 파일 형식 확인(마스킹)")
                reported.add(situation)
        # 파일 목록(#10): 크롤링이 연 폴더는 _check_crawled_pages가 본다. 링크가 없는 흔한 업로드 폴더만 더 연다
        for path in ("/uploads/", "/upload/", "/files/", "/data/", "/backup/"):
            r = await http.get_cached(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and hm is not None:
                hm.pages.setdefault(path, r)

    # ---------------------------------------------------------------- #11
    async def _check_error_page(self, ctx, http, a: Asset) -> Fetched | None:
        """#11을 보고, 없는 주소에 200으로 답하면 그 응답을 돌려준다(이후 경로 점검의 비교 기준)."""
        r = await http.get(f"https://{a.host}/a2d-check-{_token()}")
        if r is None:
            return None
        low = r.text.lower()
        if r.status >= 500 or "traceback" in low or "stack trace" in low or "sqlalchemy" in low:
            self._add(ctx, a, 11, "basic", f"GET {r.url}",
                      f"없는 주소에 오류 {r.status}, 내부 코드 기록·경로 노출(마스킹)")
        return r if r.status == 200 else None

    # ---------------------------------------------------------------- #12 #13
    async def _check_code(self, ctx, http, a: Asset, hm: HostMap) -> None:
        """크롤링으로 연 모든 화면 HTML(인라인 스크립트·__NEXT_DATA__)과 JS에서 비밀키를 찾는다(#12).

        같은 종류의 키는 자산당 처음 본 곳 한 건으로 센다. JS의 소스맵이 열려 있으면 #13(자산당 한 건)으로 남기고,
        코드에 없던 키가 소스맵 안에 있으면 #12로 따로 보고한다.
        """
        reported: set[str] = set()
        sources = [(r.url, r.text, "화면 HTML") for _, r in sorted(hm.html_pages()) if r.status == 200]
        sources += [(u, r.text, "화면 코드") for u, r in sorted(hm.scripts.items())]
        for url, text, where in sources:
            kinds = [k for k in _secret_kinds(text) if k not in reported]
            if kinds:
                reported |= set(kinds)
                self._add(ctx, a, 12, "secret", f"GET {url}", _clip(f"{where}에 {'·'.join(kinds)} 형태 키 노출(마스킹)"))
        maps: list[Fetched] = []
        for url, js in sorted(hm.scripts.items()):
            map_url = _sourcemap_url(js.text, url)
            if map_url is None or not map_url.startswith(f"https://{a.host}/"):
                continue  # 소스맵이 없거나, 코드 안에 들어 있거나(data:), 다른 곳에 있다
            mapr = await http.get_cached(map_url, max_bytes=SOURCEMAP_MAX_BYTES)
            if mapr is None or mapr.status != 200 or not _is_sourcemap(mapr):
                continue  # 모르는 경로를 index.html로 돌려주는 SPA는 소스맵 공개가 아니다
            maps.append(mapr)
            kinds = [k for k in _secret_kinds(mapr.text) if k not in reported]
            if kinds:
                reported |= set(kinds)
                self._add(ctx, a, 12, "secret", f"GET {mapr.url}",
                          _clip(f"소스맵 안에 {'·'.join(kinds)} 형태 키 노출(마스킹)"))
        if maps:
            self._add(ctx, a, 13, "basic", f"GET {maps[0].url}",
                      _clip(f"소스맵(.map) {len(maps)}개 공개" if len(maps) > 1 else "소스맵(.map) 공개"))

    # ---------------------------------------------------------------- 크롤링한 페이지 #10 #11 #18
    def _check_crawled_pages(self, ctx, a: Asset, hm: HostMap, *, primary: bool) -> None:
        listing: tuple[str, Fetched] | None = None
        error: tuple[str, Fetched] | None = None
        for path, r in sorted(hm.pages.items()):
            low = r.text.lower()
            if r.status == 200 and "index of" in low and _is_html(r):
                if listing is None or (SENSITIVE_NAME.search(r.text) and not SENSITIVE_NAME.search(listing[1].text)):
                    listing = (path, r)
            if error is None and (r.status >= 500 or "traceback (most recent call last)" in low
                                  or "stack trace" in low or "sqlalchemy" in low or "fatal error</b>" in low):
                error = (path, r)
        if listing is not None:
            situation = "sensitive" if SENSITIVE_NAME.search(listing[1].text) else "basic"
            self._add(ctx, a, 10, situation, f"GET {listing[1].url}", "디렉터리 목록 공개(파일 이름 마스킹)")
        if error is not None and 11 not in a.reported:
            self._add(ctx, a, 11, "basic", f"GET {error[1].url}",
                      _clip(f"{error[0]}에서 오류 {error[1].status}, 내부 코드 기록·경로 노출(마스킹)"))

    def _check_crawled_admin(self, ctx, a: Asset, hm: HostMap) -> bool:
        for path, r in sorted(hm.pages.items()):
            if r.status != 200 or not _is_html(r) or not _is_login(r.text):
                continue
            if _ADMIN_PATH.search(path) or _ADMIN_TITLE.search(r.text) or "관리자" in r.text:
                self._add(ctx, a, 18, "basic", f"GET {r.url}", _clip(f"{path}에 관리자 로그인 화면 노출"))
                return True
        return False

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
                self._add(ctx, a, 20, "env", f"GET {r.url}", f"{path} 공개, 환경 변수·비밀값 노출(마스킹)")
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
    async def _check_dev_server(self, ctx, http, a: Asset, hm: HostMap) -> None:
        """개발·테스트 서버가 외부에 열려 있는지(#19). 개발 모드 표시(프레임워크 디버그 화면·개발 서버 스크립트·
        Go expvar)가 크롤링한 페이지나 응답 헤더에 있으면 debug로 본다."""
        r = hm.pages.get("/") or await http.get_cached(f"https://{a.host}/")
        if r is None or r.status != 200:
            return
        texts = [x.text.lower().replace(" ", "") for _, x in hm.html_pages()] + [r.text.lower().replace(" ", "")]
        marks = {m.replace(" ", "") for m in DEBUG_MARKS}
        has_debug = any(m in t for t in texts for m in marks) or bool(r.header("x-debug-token"))
        if not has_debug:
            dbg = await http.get_cached(f"https://{a.host}/debug/vars")
            has_debug = dbg is not None and dbg.status == 200 and not _is_html(dbg) and \
                any(k in dbg.text.lower() for k in ('"cmdline"', '"memstats"', '"debug": true', '"debug":true'))
        situation = "debug" if has_debug else "basic"
        self._add(ctx, a, 19, situation, f"GET {r.url}",
                  "개발·테스트 서버 외부 노출" + (", 디버그 표시 있음" if has_debug else ""))

    # ---------------------------------------------------------------- #16
    def _check_unauth_api(self, ctx, a: Asset, hm: HostMap) -> None:
        """크롤링으로 부른 API(화면·JS·robots·sitemap·API 설명서에서 찾은 GET 경로) 중 로그인 없이
        개인정보 형태를 돌려준 곳. 자산당 한 건으로 묶고 몇 곳인지 증거에 적는다."""
        hits: list[tuple[str, Fetched, list[str], int | None]] = []
        for path, r in sorted(hm.json_pages(), key=lambda x: (0 if _API_PREFIX.match(x[0]) else 1, x[0])):
            if r.status != 200:
                continue
            kinds, count = _pii_shape(r)
            if kinds:
                hits.append((path, r, kinds, count))
        if not hits:
            return
        path, r, kinds, count = hits[0]
        where = f"{count}건" if count is not None else "데이터"
        more = f" 외 {len(hits) - 1}곳({', '.join(h[0] for h in hits[1:4])})" if len(hits) > 1 else ""
        self._add(ctx, a, 16, "pii", f"GET {r.url}",
                  _clip(f"{r.status} 응답, {where}에 {'·'.join(kinds)} 형식 포함(마스킹){more}"))

    async def _probe_api_doc(self, http, a: Asset, doc: Fetched | None, hm: HostMap) -> None:
        """API 설명서(OpenAPI)에 적힌 변수 없는 GET 경로를 부르고 결과를 크롤링 기록에 더한다(#16 대상)."""
        if doc is None:
            return
        for p in _openapi_get_paths(doc):
            if p in hm.pages or UNSAFE_ROUTE.search(p):
                continue
            r = await http.get_cached(f"https://{a.host}{p}")
            if r is not None:
                hm.pages[p] = r

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

    # ================================================================ 인증서 발급 기록

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

    # ================================================================ #34 BaaS

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
                      _clip(f"공개 키로 테이블 {len(open_tables)}개 읽힘({names}). {t}에 {'·'.join(kinds)} 형식(마스킹)"))
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
                              f"Realtime Database 공개 읽기, 최상위 항목 {len(keys)}개(이름 마스킹)")
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
                detail = f", {'·'.join(kinds)} 형식(마스킹)" if kinds else ", 개인정보 형태는 아님"
                self._add(ctx, a, 34, situation, f"GET {url}",
                          _clip(f"Firestore {col} 컬렉션 공개 읽기{detail}"))
                break
        for bucket in conf.get("buckets", [])[:2]:
            url = f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o?maxResults=20"
            r = await http.get(url)
            if r is not None and r.status == 200 and '"items"' in r.text:
                situation = "sensitive" if SENSITIVE_NAME.search(r.text) else "listing"
                self._add(ctx, a, 14, situation, f"GET {url}", "Firebase Storage 파일 목록 공개(파일 이름 마스킹)")
                break

    # ---------------------------------------------------------------- #21
    async def _check_cors(self, ctx, http, a: Asset, hm: HostMap) -> None:
        """찾은 API 응답(JSON) 몇 곳에 다른 출처(Origin)를 붙여 다시 불러, 아무 출처나 자격 증명과 함께
        허용하는지 본다(#21). API를 못 찾았으면 첫 화면으로 본다."""
        evil = "https://a2d-cors-probe.example"
        paths = [p for p, r in sorted(hm.json_pages()) if r.status == 200][:CORS_PROBE_LIMIT] or ["/"]
        for path in paths:
            r = await http.get(f"https://{a.host}{path}", extra_headers={"Origin": evil})
            if r is None:
                continue
            allow = (r.header("access-control-allow-origin") or "").strip()
            creds = (r.header("access-control-allow-credentials") or "").lower() == "true"
            if allow in (evil, "null") and creds:
                self._add(ctx, a, 21, "any_origin", f"GET {r.url}",
                          "아무 Origin을 그대로 허용하며 자격 증명도 허용")
                return

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
                      "클라우드 저장소 파일 목록 공개(파일 이름 마스킹)")

    # ---------------------------------------------------------------- #6
    async def _check_dangling(self, ctx, http, a: Asset) -> None:
        """CNAME이 가리키는 외부 서비스가 '해지됨' 안내문을 내는지(#6). 그 서비스의 안내문만 본다."""
        r = await http.get(f"https://{a.host}/")
        if r is None:
            r = await http.get(f"http://{a.host}/")
        if r is None:
            return
        low = r.text.lower()
        target = (a.cname or "").rstrip(".")
        for sfxs, sign in TAKEOVER_SIGNS:
            if any(target.endswith(sfx) for sfx in sfxs) and sign in low:
                self._add(ctx, a, 6, "dangling", a.host, _clip(f"{target}의 해지된 서비스 안내문 확인"))
                return

    # ---------------------------------------------------------------- #23 #25 #30 #27 #28
    async def _check_server_wide(self, ctx, http, a: Asset) -> None:
        r = await http.get_cached(f"https://{a.host}/")
        if r is not None:
            await self._check_version(ctx, http, a, r)  # #23 #25
            self._check_headers(ctx, a, r)   # #30
        await self._check_redirect(ctx, http, a)  # #27
        await self._check_tls(ctx, a)              # #28

    async def _check_version(self, ctx, http, a: Asset, r: Fetched) -> None:
        """응답 헤더의 서버 버전을 공개 자료와 대조한다. #23은 NVD(알려진 취약점)와 CISA KEV(실제 악용),
        #25는 endoflife.date(지원 종료). 조회에 실패하면 '모름'이라 보고하지 않는다."""
        server = r.header("server") or ""
        powered = r.header("x-powered-by") or ""
        for product, version in _versions(server + " " + powered):
            vulns = await intel.cves(http, product, version)
            if vulns:
                top = vulns[:CVE_ATTACH_LIMIT]
                kev = sum(1 for v in vulns if v.get("kev"))
                shown = ", ".join(f"{v['id']}({'KEV' if v.get('kev') else 'CVSS ' + str(v.get('cvss'))})"
                                  for v in top[:3])
                self._add(ctx, a, 23, _vuln_situation(vulns), f"GET {r.url}",
                          _clip(f"서버 버전 {product} {version}, 알려진 취약점 {len(vulns)}건"
                                f"(실제 악용 {kev}건): {shown}"), cves=top)
            if await intel.end_of_life(http, product, version):
                self._add(ctx, a, 25, "server", f"GET {r.url}", f"{product} {version}은 지원이 끝난 버전")

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

    # ---------------------------------------------------------------- #33
    async def _check_domain_expiry(self, ctx: EngineContext, http: HttpClient) -> None:
        """등록 정보(RDAP)의 만료일. 공공기관처럼 만료일이 먼 미래(9999년)로 적힌 도메인은 보지 않는다."""
        domain = ctx.domain.lower().strip(".")
        reg = await intel.domain_registration(http, domain)
        expires = (reg or {}).get("expires")
        if expires is None or expires.year >= 9000:
            return
        days = (expires - dt.datetime.now(dt.timezone.utc)).days
        lock = (reg or {}).get("transfer_locked")
        tail = "" if lock is None else (", 이전 잠금 켜짐" if lock else ", 이전 잠금 꺼짐")
        if days < 0:
            situation, ev = "expired", f"도메인이 {expires:%Y-%m-%d}에 만료됨{tail}"
        elif days <= 30:
            situation, ev = "expiring30", f"도메인이 {days}일 뒤({expires:%Y-%m-%d}) 만료{tail}"
        elif days <= 90:
            situation, ev = "expiring90", f"도메인이 {days}일 뒤({expires:%Y-%m-%d}) 만료{tail}"
        else:
            return
        self._add_host(ctx, f"www.{domain}", 33, situation, f"RDAP {domain}", ev) or \
            self._add_host(ctx, domain, 33, situation, f"RDAP {domain}", ev)

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
        # 도메인 자체 발견: 루트 자산(web)에 붙인다
        host = f"www.{domain}"
        self._add_host(ctx, host, 32, situation, f"DNS {domain}", ev) or \
            self._add_host(ctx, domain, 32, situation, f"DNS {domain}", ev)

    # ---------------------------------------------------------------- 공용
    def _add(self, ctx: EngineContext, a: Asset, check_id: int, situation: str,
             location: str, evidence: str, *, cves: list[dict] | None = None) -> None:
        try:
            ctx.add_finding(RawFinding(host=a.host, check_id=check_id, situation=situation,
                                       location=location, evidence=_clip(evidence), cves=cves or []))
            a.reported.add(check_id)
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
    """#24 홈페이지 컴포넌트 식별. 이미 받은 첫 화면(본문·헤더)만 읽는다. 점수에는 넣지 않고 자산 정보에 표시한다."""
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
        add(_PRODUCT_NAMES.get(product, product), version)  # 지원 종료 여부는 자산 찾기에서 조회해 채운다
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
