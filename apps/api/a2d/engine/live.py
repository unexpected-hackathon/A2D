"""실제 대상을 읽기만 해서 점검하는 엔진(FR-02·FR-03, 상세설계 4절 "점검 1회의 실행 순서").

자산 찾기(#1~#4, #6)와 1차 점검을 정해진 순서로 돈다. LLM 없이 코드로만 동작한다.
대상에는 읽기(GET·DNS·TLS) 요청만 보내고, 발견은 ctx.add_finding으로 넘긴다. 증거는 가린 발췌만 넘긴다.

연결 통로(HTTP·DNS·TLS)는 engine.net의 구현을 쓰고, 테스트는 같은 자리에 가짜를 끼운다.
A2D_ENGINE=a2d.engine.live:LiveEngine 으로 가짜 엔진(fixture) 대신 끼운다.

지금 범위는 시연 대상(target/)에 심은 결함이다. 외부 조회(#5 인증서 기록·#33 도메인 만료)는
apps/api의 시연용 가짜 응답이 맡고, #7·#15·#22·#29는 2차, #34는 대상에 없어 다루지 않는다.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from dataclasses import dataclass, field

from ..config import Settings
from .base import Engine, EngineContext, RawAsset, RawFinding
from .net import (Dns, DnsResolver, Fetched, HttpClient, Tls, TlsInspector,
                  open_http_client)

log = logging.getLogger("a2d.engine.live")

# 자산 찾기에 쓰는 흔한 하위 도메인 이름(#1). 대상 DNS가 응답하는 것만 자산이 된다.
SUBDOMAIN_WORDS = ("www", "api", "admin", "staging", "dev", "test", "mail", "recruit", "promo",
                   "portal", "cms", "blog", "beta", "shop", "vpn", "git", "gitlab", "jenkins")

SECURITY_HEADERS = ("strict-transport-security", "content-security-policy", "x-frame-options")
# 공개돼 있으면 안 되는 운영 경로(#20). 환경 변수가 보이면 env, 상태·통계만 보이면 status.
STATUS_PATHS = (("/actuator/env", "env"), ("/server-status", "status"), ("/phpinfo.php", "status"),
                ("/metrics", "status"))
BACKUP_PATHS = ("/backup.zip", "/backup.sql", "/db.sql", "/dump.sql")
CONFIG_PATHS = (("/.env", "env"), ("/.git/HEAD", "git"), ("/.git/config", "git"))
API_DOC_PATHS = ("/openapi.json", "/swagger.json", "/swagger", "/docs", "/api-docs")
ADMIN_PATHS = ("/admin", "/admin/", "/wp-admin/", "/phpmyadmin/")

# 비밀키 앞부분 형태(#12). 값은 저장하지 않고 '있다'만 센다.
SECRET_PATTERNS = {
    "AWS 액세스 키": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Stripe 비밀키": re.compile(r"\bsk_live_[0-9A-Za-z]{10,}"),
    "토스페이먼츠 키": re.compile(r"\blive_sk_[0-9A-Za-z]{10,}"),
    "Slack 토큰": re.compile(r"\bxox[bp]-[0-9A-Za-z-]{10,}"),
    "GitHub 토큰": re.compile(r"\b(?:ghp_|github_pat_)[0-9A-Za-z_]{20,}"),
    "OpenAI 키": re.compile(r"\bsk-proj-[0-9A-Za-z_-]{10,}"),
    "Anthropic 키": re.compile(r"\bsk-ant-[0-9A-Za-z_-]{10,}"),
    "Supabase service_role 키": re.compile(r"service_role"),
}

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
_JQUERY = re.compile(r"jquery[.-]?(\d+\.\d+\.\d+)", re.I)

# 내장한 취약 버전 목록(#23). 실제 서비스라면 주기적으로 갱신한다.
KNOWN_VULNS = {
    ("apache", "2.4.49"): [{"id": "CVE-2021-41773", "cvss": 7.5, "kev": True}],
    ("apache", "2.4.50"): [{"id": "CVE-2021-42013", "cvss": 9.8, "kev": True}],
}
# 지원 종료 소프트웨어(#25). endoflife.date를 내장했다고 가정한 최소 표.
EOL = {("php", "8.1"), ("php", "8.0"), ("php", "7.4"), ("openssl", "1.1")}

EVIDENCE_LIMIT = 200


@dataclass
class Asset:
    host: str
    alias: str
    role: str  # web | api | admin | dev | external | dangling | mail
    importance: int
    importance_rule: str
    found_by: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _clip(text: str) -> str:
    return text[:EVIDENCE_LIMIT]


class LiveEngine(Engine):
    def __init__(self, settings: Settings, *, dns: Dns | None = None, tls: Tls | None = None,
                 client=None, host_min_interval: float | None = None):
        self.s = settings
        self._dns = dns if dns is not None else DnsResolver(settings.dns_servers)
        self._tls = tls if tls is not None else TlsInspector()
        self._client = client            # 테스트에서 httpx.MockTransport를 끼운다
        self._owns_client = client is None
        self._interval = host_min_interval

    async def run(self, ctx: EngineContext) -> None:
        client = self._client or open_http_client(self.s.ca_bundle or False)
        interval = self._interval if self._interval is not None else None
        http = HttpClient(ctx.budget, client) if interval is None else \
            HttpClient(ctx.budget, client, host_min_interval=interval)
        try:
            ctx.set_stage("discovering", "자산을 찾는 중", 0, 1)
            assets = await self._discover(ctx, http)
            ctx.set_stage("discovering", "자산을 찾는 중", 1, 1)

            # 같은 서비스를 가리키는 꼭짓점·www 자산에 점검이 겹치지 않게, 대표 웹 자산 하나만 깊게 본다.
            domain = ctx.domain.lower().strip(".")
            web_assets = [a for a in assets if a.role == "web"]
            primary = next((a for a in web_assets if a.host == f"www.{domain}"),
                           web_assets[0] if web_assets else None)
            primary_host = primary.host if primary else None

            total = len(assets)
            ctx.set_stage("checking", "노출을 점검하는 중", 0, total + 1)
            done = 0
            server_wide_host = primary_host or next((a.host for a in assets
                                                     if a.role in ("api", "admin")), None)
            admin_host_exists = any(a.role == "admin" for a in assets)
            for a in assets:
                ctx.budget.check()
                await self._check_asset(ctx, http, a, primary_host=primary_host,
                                        run_server_wide=a.host == server_wide_host,
                                        admin_host_exists=admin_host_exists)
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
        for host in [domain] + [f"{w}.{domain}" for w in SUBDOMAIN_WORDS]:
            ctx.budget.check()
            cname = await asyncio.to_thread(self._dns.cname, host)
            addrs = await asyncio.to_thread(self._dns.a, host)
            if not cname and not addrs:
                continue
            found[host] = self._classify(host, domain, cname)
            found[host].found_by.append(1)

        # #2 홈페이지 링크 + #3 robots·sitemap: 같은 도메인 아래 추가 호스트를 더 찾는다
        web_host = f"www.{domain}" if f"www.{domain}" in found else domain
        extra_hosts: set[str] = set()
        home = await http.get(f"https://{web_host}/")
        cloud_hosts: set[str] = set()
        if home is not None:
            extra_hosts |= self._hosts_in(home.text, domain)
            cloud_hosts |= {m.group(1).lower() for m in _CLOUD_HOST.finditer(home.text)}
            app_js = await http.get(f"https://{web_host}/static/js/app.js")
            if app_js is not None and app_js.status == 200:
                cloud_hosts |= {m.group(1).lower() for m in _CLOUD_HOST.finditer(app_js.text)}
            if web_host in found:
                found[web_host].found_by.append(2)
        robots = await http.get(f"https://{web_host}/robots.txt")
        sitemap = await http.get(f"https://{web_host}/sitemap.xml")
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
            cname = await asyncio.to_thread(self._dns.cname, host)
            if cname or await asyncio.to_thread(self._dns.a, host):
                found[host] = self._classify(host, domain, cname)
                found[host].found_by.append(2)

        # #14 클라우드 저장소: 우리 사이트가 가리키는 버킷만 자산으로 등록한다(이름 추측 금지).
        for host in sorted(cloud_hosts):
            if host not in found:
                found[host] = Asset(host, host.split(".")[0], "cloud", 5,
                                    "우리 사이트가 쓰는 클라우드 저장소", found_by=[14], tags=["cloud"])

        # 등록. 외부 ATS(#4 recruit)는 식별만 하고 자산 메모로 남긴다.
        assets = sorted(found.values(), key=lambda a: (self._role_order(a.role), a.host))
        for a in assets:
            ctx.add_asset(RawAsset(host=a.host, alias=a.alias, url=f"https://{a.host}/",
                                   found_by=sorted(set(a.found_by)), tags=a.tags,
                                   importance=a.importance, importance_rule=a.importance_rule))
        return assets

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
        if label in ("api",):
            return Asset(host, label, "api", 5, "개인정보를 다루는 API로 추정", tags=["api"])
        if label in ("admin",):
            return Asset(host, label, "admin", 4, "관리자·내부 도구", tags=["admin"])
        if label in ("staging", "dev", "test", "beta"):
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
                           admin_host_exists: bool = False) -> None:
        if a.role == "external":
            return  # #4 식별만. 3자 서비스는 점검하지 않는다
        if a.role == "dangling":
            await self._check_dangling(ctx, http, a)
            return
        if a.role == "cloud":
            await self._check_bucket(ctx, http, a)  # #14
            return
        if a.role == "mail":
            return

        if a.role == "web" and a.host == primary_host:  # 대표 웹 자산에서만(꼭짓점·www 중복 방지)
            await self._check_files(ctx, http, a)       # #8 #9 #10
            await self._check_error_page(ctx, http, a)  # #11
            await self._check_frontend(ctx, http, a)    # #12 #13 #24
            await self._check_status_pages(ctx, http, a)  # #20
            if not admin_host_exists:  # admin 하위 도메인이 따로 있으면 거기서 한 번만 본다
                await self._check_admin_path(ctx, http, a)  # #18 (www/admin)
            await self._check_cookie(ctx, http, a)      # #31
        if a.role == "api":
            await self._check_unauth_api(ctx, http, a)  # #16
            await self._check_api_docs(ctx, http, a)    # #17
            await self._check_cors(ctx, http, a)        # #21
        if a.role == "admin":
            await self._check_admin_host(ctx, http, a)  # #18
        if a.role == "dev":
            await self._check_dev_server(ctx, http, a)  # #19

        if run_server_wide and a.role in ("web", "api", "admin"):
            await self._check_server_wide(ctx, http, a)  # #23 #25 #30 #27 #28

    # ---------------------------------------------------------------- #8 #9 #10
    async def _check_files(self, ctx, http, a: Asset) -> None:
        for path in BACKUP_PATHS:
            r = await http.get(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and _looks_like_file(r):
                self._add(ctx, a, 8, "confirmed", f"GET {r.url}",
                          f"{path} 200 응답, 파일 형식 확인(가림)")
                break  # 자산당 한 건
        for path, situation in CONFIG_PATHS:
            r = await http.get(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and r.text.strip():
                self._add(ctx, a, 9, situation, f"GET {r.url}", f"{path} 200 응답(가림)")
        r = await http.get(f"https://{a.host}/uploads/")
        if r is not None and r.status == 200 and "index of" in r.text.lower():
            situation = "sensitive" if SENSITIVE_NAME.search(r.text) else "basic"
            self._add(ctx, a, 10, situation, f"GET {r.url}", "디렉터리 목록 공개(파일 이름 가림)")

    # ---------------------------------------------------------------- #11
    async def _check_error_page(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"https://{a.host}/a2d-check-{_token()}")
        if r is None:
            return
        low = r.text.lower()
        if r.status >= 500 or "traceback" in low or "stack trace" in low or "sqlalchemy" in low:
            self._add(ctx, a, 11, "basic", f"GET {r.url}",
                      f"없는 주소에 오류 {r.status}, 내부 코드 기록·경로 노출(가림)")

    # ---------------------------------------------------------------- #12 #13 #24
    async def _check_frontend(self, ctx, http, a: Asset) -> None:
        home = await http.get(f"https://{a.host}/")
        if home is None:
            return
        self._identify_components(home)  # #24: 로그만. 점수 미반영
        scripts = set(re.findall(r'src=["\']([^"\']+\.js)["\']', home.text))
        scripts.add("/static/js/app.js")
        checked = 0
        for src in sorted(scripts):
            if checked >= 5:
                break
            url = src if src.startswith("http") else f"https://{a.host}{_abs(src)}"
            if not url.startswith(f"https://{a.host}"):
                continue
            js = await http.get(url)
            checked += 1
            if js is None or js.status != 200:
                continue
            kinds = _secret_kinds(js.text)
            if kinds:
                self._add(ctx, a, 12, "secret", f"GET {js.url}",
                          f"화면 코드에 {'·'.join(kinds)} 형태 키 노출(가림)")
            if "sourcemappingurl" in js.text.lower():
                mapr = await http.get(url + ".map")
                if mapr is not None and mapr.status == 200:
                    msecret = _secret_kinds(mapr.text)
                    if msecret:
                        self._add(ctx, a, 12, "secret", f"GET {mapr.url}",
                                  f"소스맵 안에 {'·'.join(msecret)} 형태 키 노출(가림)")
                    else:
                        self._add(ctx, a, 13, "basic", f"GET {mapr.url}", "소스맵(.map) 공개")

    # ---------------------------------------------------------------- #20
    async def _check_status_pages(self, ctx, http, a: Asset) -> None:
        for path, situation in STATUS_PATHS:
            r = await http.get(f"https://{a.host}{path}")
            if r is None or r.status != 200:
                continue
            low = r.text.lower()
            if path == "/actuator/env" or "password" in low or "secret" in low or "db_" in low:
                self._add(ctx, a, 20, "env", f"GET {r.url}", f"{path} 공개, 환경 변수·비밀값 노출(가림)")
            else:
                self._add(ctx, a, 20, "status", f"GET {r.url}", f"{path} 공개, 서버 상태·통계 노출")

    # ---------------------------------------------------------------- #18
    async def _check_admin_path(self, ctx, http, a: Asset) -> None:
        for path in ("/admin", "/admin/"):
            r = await http.get(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and _is_login(r.text):
                self._add(ctx, a, 18, "basic", f"GET {r.url}", f"{path}에 관리자 로그인 화면 노출")
                return

    async def _check_admin_host(self, ctx, http, a: Asset) -> None:
        r = await http.get(f"https://{a.host}/")
        if r is not None and r.status == 200 and _is_login(r.text):
            self._add(ctx, a, 18, "basic", f"GET {r.url}", "관리자 로그인 화면이 외부에 노출")

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
    async def _check_unauth_api(self, ctx, http, a: Asset) -> None:
        for path in ("/api/v1/applicants", "/api/v1/members", "/api/v1/users"):
            r = await http.get(f"https://{a.host}{path}")
            if r is None or r.status in (401, 403):
                continue
            if r.status != 200:
                continue
            kinds, count = _pii_shape(r)
            if kinds:
                where = f"{count}건" if count is not None else "데이터"
                self._add(ctx, a, 16, "pii", f"GET {r.url}",
                          _clip(f"{r.status} 응답, {where}에 {'·'.join(kinds)} 형식 포함(가림)"))
                return

    # ---------------------------------------------------------------- #17
    async def _check_api_docs(self, ctx, http, a: Asset) -> None:
        for path in API_DOC_PATHS:
            r = await http.get(f"https://{a.host}{path}")
            if r is not None and r.status == 200 and _is_api_doc(r):
                self._add(ctx, a, 17, "basic", f"GET {r.url}", f"{path} API 설명서 공개")
                return

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
        cookie = r.header("set-cookie")
        if not cookie:
            return
        low = cookie.lower()
        missing = [x for x in ("secure", "httponly", "samesite") if x not in low]
        if missing:
            name = cookie.split("=", 1)[0].strip().lower()
            session = any(k in name for k in ("session", "sess", "sid", "auth", "token"))
            self._add(ctx, a, 31, "login" if session else "other", f"GET {r.url}",
                      f"쿠키에 {'·'.join(missing)} 속성 누락")

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
        info = await asyncio.to_thread(self._tls.inspect, a.host)  # TLS 핸드셰이크는 블로킹
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
        elif info.self_signed or not info.hostname_ok:
            situation = "invalid"
            ev = "자체 서명이거나 이름이 맞지 않는 인증서"
        else:
            return
        self._add(ctx, a, 28, situation, f"TLS https://{a.host}", ev)

    # ---------------------------------------------------------------- #32
    async def _check_mail(self, ctx: EngineContext) -> None:
        domain = ctx.domain.lower().strip(".")
        spf = _find_txt(await asyncio.to_thread(self._dns.txt, domain), "v=spf1")
        dmarc = _find_txt(await asyncio.to_thread(self._dns.txt, f"_dmarc.{domain}"), "v=dmarc1")
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

    def _identify_components(self, home: Fetched) -> None:
        comps = []
        m = _GENERATOR.search(home.text)
        if m:
            comps.append(m.group(1).strip())
        jm = _JQUERY.search(home.text)
        if jm:
            comps.append(f"jQuery {jm.group(1)}")
        if comps:
            log.info("#24 부품 식별(%s): %s", home.url, ", ".join(comps))


# ==================================================================== 보조 함수

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


def _secret_kinds(text: str) -> list[str]:
    """비밀키 형태를 센다. 공개용 키(pk_live_·AIza 등)만 있고 비밀키가 없으면 빈 목록."""
    return [name for name, pat in SECRET_PATTERNS.items() if pat.search(text)]


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
