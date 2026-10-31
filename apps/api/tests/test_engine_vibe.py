"""바이브코딩·외주로 만든 서비스에서 실제로 사고가 나는 노출을 찾는지 본다.

- #34 Supabase RLS 꺼짐(화면 코드의 공개 키로 테이블이 읽힘), Firebase 공개 읽기
- #16 화면 JS·robots·sitemap에서 찾은 API 경로(고정 목록 밖)
- #8 robots에 적힌 백업 파일, #9 sftp.json·설정 백업, #17 GraphQL 스키마 조회
- #12 AI·메일 키와 비밀번호가 든 DB 접속 주소, #5 인증서 발급 기록

대상은 흔한 SPA 배포처럼 모르는 경로에 200 index.html을 준다(오탐 방지 조건).
"""

import asyncio
import base64
import json

import httpx

from a2d.config import Settings
from a2d.engine.base import Budget, EngineContext
from a2d.engine.live import LiveEngine, _secret_kinds
from a2d.engine.net import Fetched
from tests.test_engine_spa import SAFE_HEADERS, SafeTls, SpaDns

DOMAIN = "shop.example"
WWW = f"www.{DOMAIN}"
REF = "abcdefghijklmnopqrst"
SUPA = f"{REF}.supabase.co"
RTDB = "https://shop-app-default-rtdb.firebaseio.com"


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


ANON = f"{_b64({'alg': 'HS256', 'typ': 'JWT'})}.{_b64({'iss': 'supabase', 'ref': REF, 'role': 'anon'})}.signature123"
INDEX = ('<!doctype html><html><head><title>My Shop</title></head><body><div id="root"></div>'
         '<script type="module" src="/assets/index-3f2a.js"></script></body></html>')


class FakeVibe:
    """SPA + Supabase/Firebase. pages는 {(호스트, 경로): (상태, 본문, 형식)}. rls_off면 Supabase 테이블이 열린다."""

    def __init__(self, js: str = "", pages: dict | None = None, rls_off: bool = False):
        self.js = js
        self.pages = pages or {}
        self.rls_off = rls_off
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if request.url.scheme == "http":
            return httpx.Response(301, headers={"location": f"https://{host}{path}"})
        if (host, path) in self.pages:
            status, body, media = self.pages[(host, path)]
            return httpx.Response(status, text=body, headers={**SAFE_HEADERS, "content-type": media})
        if host == SUPA:
            return self._supabase(request)
        if host not in (DOMAIN, WWW):
            return httpx.Response(404, text="not found")
        if path == "/assets/index-3f2a.js":
            return httpx.Response(200, text=self.js,
                                  headers={**SAFE_HEADERS, "content-type": "application/javascript"})
        return httpx.Response(200, text=INDEX, headers={**SAFE_HEADERS, "content-type": "text/html"})

    def _supabase(self, request):
        if request.headers.get("apikey") != ANON:
            return httpx.Response(401, json={"message": "No API key found in request"})
        path = request.url.path
        if path == "/rest/v1/":
            return httpx.Response(200, json={"swagger": "2.0", "paths": {
                "/": {}, "/todos": {"get": {}}, "/profiles": {"get": {}}, "/rpc/stats": {"post": {}}}})
        rows = {"/rest/v1/profiles": [{"id": 1, "email": "kim@example.com", "phone": "010-1234-5678"}],
                "/rest/v1/todos": [{"id": 1, "title": "buy milk"}]}
        if path in rows:
            return httpx.Response(200, json=rows[path] if self.rls_off else [])
        return httpx.Response(404, json={"message": "relation does not exist"})


def scan(target: FakeVibe, requests_limit: int = 400):
    client = httpx.AsyncClient(transport=httpx.MockTransport(target))
    engine = LiveEngine(Settings(), dns=SpaDns(), tls=SafeTls(), client=client, host_min_interval=0)
    assets, findings = {}, []

    def add_asset(a):
        assets[a.host] = a
        return f"A-{len(assets):03d}"

    def add_finding(f):
        f.validate()
        assert f.host in assets, f"등록되지 않은 자산: {f.host}"
        findings.append(f)
        return f"F-{len(findings):04d}", "A-001"

    budget = Budget(requests_limit, 20, 300)
    ctx = EngineContext("S-1", DOMAIN, 1, budget, lambda *a: None, add_asset, add_finding,
                        lambda *a, **k: None)
    asyncio.run(engine.run(ctx))
    asyncio.run(client.aclose())
    return assets, findings, budget


def found(findings):
    return {(f.check_id, f.situation) for f in findings}


SUPABASE_JS = f'const supabase = createClient("https://{SUPA}", "{ANON}");\n'


# ------------------------------------------------------------------ #34 Supabase·Firebase

def test_supabase_rls_off_reports_pii_table():
    assets, findings, _ = scan(FakeVibe(SUPABASE_JS, rls_off=True))
    assert SUPA in assets and "baas" in assets[SUPA].tags
    f = next(f for f in findings if f.check_id == 34)
    assert f.situation == "pii" and f.host == SUPA
    assert "profiles" in f.evidence and "kim@" not in f.evidence and "010-1234" not in f.evidence


def test_supabase_rls_on_is_clean():
    _, findings, _ = scan(FakeVibe(SUPABASE_JS, rls_off=False))
    assert found(findings) == set()


def test_supabase_reads_only_one_row_with_get():
    target = FakeVibe(SUPABASE_JS, rls_off=True)
    scan(target)
    supa = [r for r in target.requests if r.url.host == SUPA]
    assert supa and {r.method for r in supa} == {"GET"}
    assert all("limit=1" in str(r.url) for r in supa if r.url.path not in ("/rest/v1/",))
    assert not any("/rpc/" in r.url.path for r in supa)  # 함수 호출(rpc)은 부르지 않는다


def test_firebase_open_database_and_storage():
    js = (f'const firebaseConfig = {{ apiKey: "AIzaSyD-public-web-key", projectId: "shop-app", '
          f'databaseURL: "{RTDB}", storageBucket: "shop-app.appspot.com" }};')
    pages = {
        ("shop-app-default-rtdb.firebaseio.com", "/.json"): (200, json.dumps({"users": True, "orders": True}),
                                                              "application/json"),
        ("firebasestorage.googleapis.com", "/v0/b/shop-app.appspot.com/o"): (
            200, json.dumps({"items": [{"name": "uploads/resume_kim.pdf"}]}), "application/json"),
    }
    assets, findings, _ = scan(FakeVibe(js, pages))
    assert "shop-app.firebaseapp.com" in assets
    assert {(34, "firebase"), (14, "sensitive")} <= found(findings)


# ------------------------------------------------------------------ #16 찾은 경로

def test_api_route_found_in_js_is_checked():
    js = 'fetch("/api/customers/list").then(r => r.json());\n'
    pages = {(WWW, "/api/customers/list"): (200, json.dumps([{"name": "김민준", "email": "a@example.com"}]),
                                            "application/json")}
    _, findings, _ = scan(FakeVibe(js, pages))
    f = next(f for f in findings if f.check_id == 16)
    assert f.host == WWW and "/api/customers/list" in f.location


def test_route_in_robots_is_checked():
    pages = {(WWW, "/robots.txt"): (200, "User-agent: *\nDisallow: /v2/export/members\n", "text/plain"),
             (WWW, "/v2/export/members"): (200, json.dumps({"data": [{"email": "a@example.com",
                                                                     "phone": "010-0000-0001"}]}),
                                           "application/json")}
    _, findings, _ = scan(FakeVibe("", pages))
    assert (16, "pii") in found(findings)


def test_state_changing_routes_are_not_called():
    js = ('fetch("/api/auth/logout"); fetch("/api/users/delete"); fetch("/api/payments/confirm");'
          'fetch("/api/products");')
    target = FakeVibe(js)
    scan(target)
    called = {r.url.path for r in target.requests}
    assert "/api/products" in called
    assert not called & {"/api/auth/logout", "/api/users/delete", "/api/payments/confirm"}


def test_public_non_pii_api_is_not_reported():
    js = 'fetch("/api/products");'
    pages = {(WWW, "/api/products"): (200, json.dumps([{"id": 1, "title": "티셔츠", "price": 9900}]),
                                      "application/json")}
    _, findings, _ = scan(FakeVibe(js, pages))
    assert found(findings) == set()


# ------------------------------------------------------------------ #8 #9 #17

def test_backup_listed_in_robots_is_found():
    pages = {(WWW, "/robots.txt"): (200, "User-agent: *\nDisallow: /old/site_2023.tar.gz\n", "text/plain"),
             (WWW, "/old/site_2023.tar.gz"): (200, "\x1f\x8b binary", "application/gzip")}
    _, findings, _ = scan(FakeVibe("", pages))
    f = next(f for f in findings if f.check_id == 8)
    assert "site_2023.tar.gz" in f.location


def test_sftp_config_from_outsourced_dev_is_found():
    sftp = json.dumps({"name": "prod", "host": "203.0.113.10", "protocol": "sftp", "username": "deploy",
                       "password": "Winter2026!", "remotePath": "/var/www"})
    _, findings, _ = scan(FakeVibe("", {(WWW, "/.vscode/sftp.json"): (200, sftp, "application/json")}))
    f = next(f for f in findings if f.check_id == 9)
    assert f.situation == "sftp" and "Winter2026" not in f.evidence


def test_graphql_introspection_open():
    body = json.dumps({"data": {"__schema": {"queryType": {"name": "Query"}}}})
    _, findings, _ = scan(FakeVibe("", {(WWW, "/api/graphql"): (200, body, "application/json")}))
    assert (17, "graphql") in found(findings)


def test_request_budget_is_respected():
    js = "".join(f'fetch("/api/r{i}");' for i in range(100))
    _, _, budget = scan(FakeVibe(js, rls_off=True), requests_limit=60)
    assert budget.requests_used <= 60


# ------------------------------------------------------------------ #12 비밀키

def test_ai_keys_and_db_urls_detected():
    groq = "gsk_" + "A1b2C3d4" * 6
    db = "postgresql://postgres:" + "Sup3rS3cret" + "@db.abcdefghijklmnopqrst.supabase.co:5432/postgres"
    kinds = _secret_kinds(f'const k="{groq}"; const u="{db}";')
    assert "Groq 키" in kinds and "DB 접속 주소(비밀번호 포함)" in kinds


def test_dummy_db_urls_are_not_secrets():
    for u in ("postgres://user:password@localhost:5432/app", "mysql://root:${DB_PASS}@db:3306/x",
              "mongodb+srv://<user>:<password>@cluster0.example.mongodb.net"):
        assert _secret_kinds(f'"{u}"') == [], u


def test_secret_in_next_data_html_is_found():
    key = "sk-proj-" + "Zz9" * 10
    html = (f'<!doctype html><html><body><script id="__NEXT_DATA__" type="application/json">'
            f'{{"props":{{"pageProps":{{"openaiKey":"{key}"}}}}}}</script></body></html>')
    target = FakeVibe("", {(WWW, "/"): (200, html, "text/html")})
    _, findings, _ = scan(target)
    f = next(f for f in findings if f.check_id == 12)
    assert "OpenAI" in f.evidence and key not in f.evidence


# ------------------------------------------------------------------ #5 인증서 발급 기록

class _CtHttp:
    def __init__(self, body: str, status: int = 200):
        self.body, self.status, self.urls = body, status, []

    async def get(self, url, extra_headers=None, *, timeout=10.0):
        self.urls.append(url)
        return Fetched(url=url, status=self.status, headers={"content-type": "application/json"},
                       text=self.body, scheme="https")


def test_ct_names_filtered_to_own_domain():
    body = json.dumps([{"name_value": "api-prod.shop.co.kr\n*.shop.co.kr"},
                       {"common_name": "partner.shop.co.kr"}, {"name_value": "evil.example.com"}])
    http = _CtHttp(body[:-30])  # 응답이 잘려도 읽는다
    engine = LiveEngine(Settings(), dns=SpaDns(), tls=SafeTls(), client=object(), host_min_interval=0)
    names = asyncio.run(engine._ct_names(http, "shop.co.kr"))
    assert "api-prod.shop.co.kr" in names and "evil.example.com" not in names
    assert all(n.endswith(".shop.co.kr") for n in names)


def test_ct_not_queried_for_reserved_domains():
    http = _CtHttp("[]")
    engine = LiveEngine(Settings(), dns=SpaDns(), tls=SafeTls(), client=object(), host_min_interval=0)
    assert asyncio.run(engine._ct_names(http, "jobnest.test")) == [] and http.urls == []


def test_ct_name_with_api_word_is_classified_as_api():
    engine = LiveEngine(Settings(), dns=SpaDns(), tls=SafeTls(), client=object(), host_min_interval=0)
    assert engine._classify("api-prod.shop.co.kr", "shop.co.kr", None).role == "api"
    assert engine._classify("dev-api.shop.co.kr", "shop.co.kr", None).role == "dev"
    assert engine._classify("admin2.shop.co.kr", "shop.co.kr", None).role == "admin"
