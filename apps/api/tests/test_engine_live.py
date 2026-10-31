"""실제 점검 엔진(LiveEngine)을 가짜 대상으로 확인한다.

httpx.MockTransport로 시연 대상(target/jobnest)의 응답을, 가짜 DNS·TLS로 영역·인증서를 흉내 낸다.
실제 네트워크는 쓰지 않는다. 결함을 모두 켠 상태에서 심은 결함을 찾고, 모두 고친 상태에서는
발견이 없어야 한다. 증거에 개인정보 원문이 없고, User-Agent와 요청 예산이 지켜지는지도 본다.
"""

import datetime as dt
import json

import httpx
import pytest

from a2d.config import Settings
from a2d.engine.base import Budget, EngineContext, RawAsset, RawFinding
from a2d.engine.live import LiveEngine
from a2d.engine import intel
from a2d.engine.net import USER_AGENT, CertInfo
from tests.test_engine_intel import KEV, NVD_APACHE, NVD_EMPTY, eol_v1

DOMAIN = "jobnest.test"
PROXY = "10.253.53.80"
EXT_BUCKET = "jobnest-resumes.s3.ap-northeast-2.amazonaws.com"
EXT_PAGES = "jobnest-promo.github.io"
EXT_BOOKING = "jobnest.atspartner.test"

APPLICANTS = {"page": 1, "total": 40, "items": [
    {"id": 1, "name": "김민준", "email": "applicant001@example.com", "phone": "010-0000-0001"},
    {"id": 2, "name": "이서연", "email": "applicant002@example.com", "phone": "010-0000-0002"},
]}

def app_js(leak: bool, sourcemap: bool) -> str:
    """target/jobnest의 app.js처럼 leak이면 비밀키를, sourcemap이면 소스맵 주석을 넣는다."""
    # 비밀키 형태 문자열을 저장소에 그대로 두지 않으려고 실행 중에 이어 붙인다(target/config.py와 같은 방식)
    cfg = (f'  aws: {{ bucket: "jobnest-resumes", accessKeyId: "{"AKIA" + "ZZ2QWERTY9ABCDEF"}" }},\n'
           '  payments: { stripeKey: "sk_live_abcdEFGH1234ijklMNOP" }\n' if leak else "")
    js = (f'var JN_CONFIG = {{ apiBase: "https://api.{DOMAIN}",\n{cfg}}};\n'
          f'fetch(JN_CONFIG.apiBase + "/api/v1/applicants?page=1");\n')
    if sourcemap:
        js += "//# sourceMappingURL=app.js.map\n"
    return js

HOME_HTML = f"""<!doctype html><html><head><meta name="generator" content="JobNest CMS 2.3"></head>
<body><a href="https://api.{DOMAIN}/api/v1/status">상태</a>
<a href="https://recruit.{DOMAIN}/">위탁</a> <a href="https://promo.{DOMAIN}/">이벤트</a>
<img src="http://{EXT_BUCKET}/banners/x.jpg">
<script src="/static/js/jquery-1.12.4.min.js"></script><script src="/static/js/app.js"></script></body></html>"""

UPLOADS = "<html><title>Index of /uploads</title><a href='resume_0012.pdf'>resume_0012.pdf</a></html>"
TRACEBACK = ("<h1>Error 500</h1><pre>Traceback (most recent call last):\n"
             "sqlalchemy.orm.exc.NoResultFound\npymysql.err at 10.0.12.5</pre>")
ACTUATOR = json.dumps({"propertySources": [{"properties": {"DB_PASSWORD": {"value": "secret"}}}]})
SERVER_STATUS = "<h1>Apache Server Status</h1><dt>Total accesses: 1832044</dt>"
ADMIN_LOGIN = '<h2>채용 담당자 콘솔</h2><form><input name="password" type="password"></form>'
STAGING = '<div class="banner">⚠ STAGING · DEBUG=True · 운영 지원자 DB 복제본</div>'
BUCKET_XML = ("<ListBucketResult><Name>jobnest-resumes</Name>"
              "<Contents><Key>backups/jobnest_prod_2026-09-30.sql.gz</Key></Contents>"
              "<Contents><Key>resumes/0012.pdf</Key></Contents></ListBucketResult>")
PAGES_404 = "<h1>404</h1><p><strong>There isn't a GitHub Pages site here.</strong></p>"


class FakeTarget:
    """결함 토글(fixed set)에 따라 target/jobnest 응답을 흉내 낸다. 요청을 기록한다."""

    def __init__(self, fixed: set[int]):
        self.fixed = fixed
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        path = request.url.path
        scheme = request.url.scheme
        fx = self.fixed

        common = {"server": "Apache" if 23 in fx else "Apache/2.4.49 (Unix)"}
        if 25 not in fx:
            common["x-powered-by"] = "PHP/8.1.2"
        if 30 in fx:
            common.update({"strict-transport-security": "max-age=31536000",
                           "content-security-policy": "default-src 'self'", "x-frame-options": "DENY"})

        def resp(status, body, headers=None, media="text/html"):
            h = dict(common)
            h.update(headers or {})
            if isinstance(body, dict):
                return httpx.Response(status, json=body, headers=h)
            return httpx.Response(status, text=body, headers={**h, "content-type": media})

        # 공개 자료 조회(#23 NVD·KEV, #25 endoflife.date). 실제 응답 꼴은 test_engine_intel의 것을 쓴다
        if host == "services.nvd.nist.gov":
            url = str(request.url)
            return httpx.Response(200, json=NVD_APACHE if ("http_server" in url and "2.4.49" in url) else NVD_EMPTY)
        if host == "www.cisa.gov":
            return httpx.Response(200, json=KEV)
        if host == "endoflife.date":
            if path.endswith("/php"):
                return httpx.Response(200, json=eol_v1("php", [("8.2", False, None), ("8.1", True, "2025-12-31")]))
            if path.endswith("/apache-http-server"):
                return httpx.Response(200, json=eol_v1("apache-http-server", [("2.4", False, None)]))
            return httpx.Response(404, text="nf")

        # 외부 주소
        if host == EXT_PAGES or host == f"promo.{DOMAIN}":
            return resp(404, PAGES_404, {"server": "GitHub.com"})
        if host == EXT_BUCKET:
            if 14 in fx:
                return resp(403, "<Error><Code>AccessDenied</Code></Error>", {"server": "AmazonS3"}, "application/xml")
            return resp(200, BUCKET_XML, {"server": "AmazonS3"}, "application/xml")
        if host in (EXT_BOOKING, f"recruit.{DOMAIN}"):
            return resp(200, "<html>ATSPartner</html>")

        # HTTP → HTTPS 전환(#27)
        if scheme == "http":
            if 27 in fx:
                return httpx.Response(301, headers={"location": f"https://{host}{path}"})
            return resp(200, "<html>home over http</html>")

        if host == f"api.{DOMAIN}":
            return self._api(path, request, resp, fx)
        if host == f"admin.{DOMAIN}":
            if path in ("/", "/admin", "/login") and 18 not in fx:
                return resp(200, ADMIN_LOGIN)
            return resp(403, "blocked") if 18 in fx else resp(404, "nf")
        if host in (f"staging.{DOMAIN}", f"dev.{DOMAIN}", f"test.{DOMAIN}"):
            if 19 in fx:
                return resp(403, "blocked")
            if path == "/debug/vars":
                return resp(200, {"DEBUG": True, "DATABASE_URL": "mysql://..."})
            return resp(200, STAGING)
        if host in (f"www.{DOMAIN}", DOMAIN):
            return self._www(path, resp, fx)
        if host == f"mail.{DOMAIN}":
            return resp(404, "unknown host")
        return resp(404, "nf")

    def _www(self, path, resp, fx):
        cookie = ("jn_session=x; HttpOnly; Secure; SameSite=lax" if 31 in fx else "jn_session=x")
        if path == "/":
            return resp(200, HOME_HTML, {"set-cookie": cookie})
        if path == "/robots.txt":
            return resp(200, f"User-agent: *\nDisallow: /admin/\nDisallow: /internal/reports/\n"
                             f"Sitemap: https://www.{DOMAIN}/sitemap.xml", media="text/plain")
        # target/jobnest처럼 robots가 가리키는 사내 보고서 목록과, 거기서 링크로 가는 지원자 내보내기(#16과 같은 조치)
        if path == "/internal/reports/":
            return resp(401, {"detail": "인증이 필요합니다"}) if 16 in fx else \
                resp(200, '<html><a href="/internal/reports/export">지원자 내보내기</a></html>')
        if path == "/internal/reports/export":
            return resp(401, {"detail": "인증이 필요합니다"}) if 16 in fx else resp(200, APPLICANTS)
        if path == "/sitemap.xml":
            return resp(200, "<urlset><url><loc>/</loc></url></urlset>", media="application/xml")
        if path == "/static/js/app.js":
            return resp(200, app_js(leak=12 not in fx, sourcemap=13 not in fx), media="application/javascript")
        if path == "/static/js/app.js.map":
            if 13 in fx:
                return resp(404, "nf")
            return resp(200, json.dumps({"sourcesContent": [app_js(leak=12 not in fx, sourcemap=False)]}),
                        media="application/json")
        if path in ("/backup.zip", "/db.sql"):
            return resp(404, "nf") if 8 in fx else resp(200, "PK\x03\x04zipdata", media="application/zip")
        if path in ("/.env", "/.git/HEAD", "/.git/config"):
            body = {"/.env": "SECRET=1\n", "/.git/HEAD": "ref: refs/heads/main\n",
                    "/.git/config": "[core]\n\tbare = false\n"}[path]
            return resp(404, "nf") if 9 in fx else resp(200, body, media="text/plain")
        if path == "/uploads/":
            return resp(403, "blocked") if 10 in fx else resp(200, UPLOADS)
        if path == "/server-status":
            return resp(404, "nf") if 20 in fx else resp(200, SERVER_STATUS)
        if path == "/actuator/env":
            return resp(404, "nf") if 20 in fx else resp(200, ACTUATOR, media="application/json")
        if path in ("/admin", "/admin/"):
            return resp(403, "blocked") if 18 in fx else resp(200, ADMIN_LOGIN)
        # 없는 주소(#11)
        if 11 in fx:
            return resp(404, "페이지를 찾을 수 없습니다")
        return resp(500, TRACEBACK)

    def _api(self, path, request, resp, fx):
        if path == "/api/v1/status":
            origin = request.headers.get("origin")
            h = {}
            if origin:
                if 21 in fx:
                    if origin in (f"https://www.{DOMAIN}", f"https://{DOMAIN}"):
                        h = {"access-control-allow-origin": origin, "access-control-allow-credentials": "true"}
                else:
                    h = {"access-control-allow-origin": origin, "access-control-allow-credentials": "true"}
            return resp(200, {"status": "ok"}, h)
        if path == "/api/v1/applicants":
            if 16 in fx:
                return resp(401, {"detail": "인증이 필요합니다"})
            return resp(200, APPLICANTS)
        if path in ("/openapi.json", "/swagger"):
            return resp(404, "nf") if 17 in fx else resp(200, {"openapi": "3.0.0", "paths": {
                "/api/v1/status": {"get": {}}, "/api/v1/applicants": {"get": {}},
                "/api/v1/applicants/{applicant_id}": {"get": {}}}})
        return resp(404, "nf")


class FakeDns:
    def __init__(self, fixed: set[int], test_server=False):
        self.fixed = fixed
        self.test_server = test_server

    def _hosts(self):
        hosts = {DOMAIN, f"www.{DOMAIN}", f"api.{DOMAIN}", f"admin.{DOMAIN}",
                 f"staging.{DOMAIN}", f"dev.{DOMAIN}", f"mail.{DOMAIN}"}
        if self.test_server:
            hosts.add(f"test.{DOMAIN}")
        return hosts

    def a(self, name):
        return [PROXY] if name in self._hosts() else []

    def cname(self, name):
        if name == f"recruit.{DOMAIN}":
            return EXT_BOOKING
        if name == f"promo.{DOMAIN}" and 6 not in self.fixed:
            return EXT_PAGES
        return None

    def txt(self, name):
        if name == DOMAIN:
            return ["v=spf1 include:_spf.google.com -all"] if 32 in self.fixed else ["v=spf1 +all"]
        if name == f"_dmarc.{DOMAIN}":
            return [f"v=DMARC1; p=reject; rua=mailto:dmarc@{DOMAIN}"] if 32 in self.fixed else []
        return []


class FakeTls:
    def __init__(self, fixed: set[int]):
        self.fixed = fixed

    def inspect(self, host, port=443):
        now = dt.datetime.now(dt.timezone.utc)
        if 28 in self.fixed:
            return CertInfo(not_after=now + dt.timedelta(days=365), self_signed=False, hostname_ok=True)
        return CertInfo(not_after=now + dt.timedelta(days=7), self_signed=True, hostname_ok=True)


def run_engine(fixed, *, requests_limit=0, test_server=False):
    intel.clear_caches()
    target = FakeTarget(fixed)
    client = httpx.AsyncClient(transport=httpx.MockTransport(target))
    dns = FakeDns(fixed, test_server=test_server)
    tls = FakeTls(fixed)
    engine = LiveEngine(Settings(), dns=dns, tls=tls, client=client, host_min_interval=0)

    budget = Budget(requests_limit, 20, 300)
    assets: dict[str, RawAsset] = {}
    findings: list[RawFinding] = []
    stages: list[tuple] = []

    def add_asset(a: RawAsset) -> str:
        assets[a.host.lower()] = a
        return f"A-{len(assets):03d}"

    def add_finding(f: RawFinding):
        f.validate()
        if f.host.lower() not in assets:
            raise ValueError(f"등록되지 않은 자산: {f.host}")
        findings.append(f)
        return f"F-{len(findings):04d}", "A-000"

    ctx = EngineContext("S-1", DOMAIN, 1, budget,
                        lambda *a: stages.append(a), add_asset, add_finding, lambda *a, **k: None)
    import asyncio
    asyncio.run(engine.run(ctx))
    asyncio.run(client.aclose())
    return assets, findings, budget, target


def found(findings):
    return {(f.check_id, f.situation) for f in findings}


# ------------------------------------------------------------------ 오탐 방지(리뷰 반영)

def _fetched(status=200, text="", ctype="application/json", url="https://api.jobnest.test/x"):
    from a2d.engine.net import Fetched
    return Fetched(url=url, status=status, headers={"content-type": ctype}, text=text, scheme="https")


@pytest.mark.parametrize("text, ctype", [
    (json.dumps({"order_id": "2024010123456789"}), "application/json"),   # 주문번호가 전화번호로 안 잡힘
    (json.dumps({"ts": 1701012345678}), "application/json"),             # 타임스탬프
    ("<footer>문의 support@jobnest.test</footer>", "text/html"),          # HTML 푸터 메일
    (json.dumps({"items": [{"id": 1, "title": "백엔드"}]}), "application/json"),  # 개인정보 아님
    (json.dumps({"contact": "support@jobnest.test"}), "application/json"),  # 메일 하나(필드 없음, 1종)
])
def test_pii_shape_no_false_positive(text, ctype):
    from a2d.engine.live import _pii_shape
    kinds, _ = _pii_shape(_fetched(text=text, ctype=ctype))
    assert kinds == [], f"오탐: {kinds}"


def test_pii_shape_detects_real_pii():
    from a2d.engine.live import _pii_shape
    kinds, count = _pii_shape(_fetched(text=json.dumps(APPLICANTS)))
    assert "개인정보 필드" in kinds and count == 2


def test_looks_like_file_rejects_spa_html():
    from a2d.engine.live import _looks_like_file
    assert _looks_like_file(_fetched(text="<html>index</html>", ctype="text/html")) is False
    assert _looks_like_file(_fetched(text="PK\x03\x04....", ctype="application/zip")) is True
    assert _looks_like_file(_fetched(text="-- MySQL dump\nINSERT INTO", ctype="text/plain")) is True


def test_is_api_doc_requires_openapi_marker():
    from a2d.engine.live import _is_api_doc
    assert _is_api_doc(_fetched(text=json.dumps({"openapi": "3.0.0", "paths": {}}))) is True
    assert _is_api_doc(_fetched(text="<html>사용 설명서</html>", ctype="text/html")) is False
    assert _is_api_doc(_fetched(text="<html><div id='swagger-ui'></div></html>", ctype="text/html")) is True


# ------------------------------------------------------------------ 결함 전부 켠 상태

def test_all_defects_found():
    assets, findings, budget, target = run_engine(set())
    got = found(findings)
    expected = {
        (6, "dangling"), (8, "confirmed"), (9, "env"), (9, "git"), (10, "sensitive"),
        (11, "basic"), (12, "secret"), (13, "basic"), (14, "sensitive"), (16, "pii"),
        (17, "basic"), (18, "basic"), (19, "debug"), (20, "env"), (20, "status"),
        (21, "any_origin"), (23, "kev"), (25, "server"), (27, "basic"), (28, "expiring14"),
        (30, "basic"), (31, "login"), (32, "none"),
    }
    missing = expected - got
    assert not missing, f"못 찾은 결함: {sorted(missing)}"
    # 소스맵(#13)은 키가 들어 있어도 #13으로 남고, 그 키는 코드 쪽 #12 한 건으로 센다.


def test_sourcemap_without_keys_reports_13():
    assets, findings, _, _ = run_engine({12})  # 키는 치웠지만 소스맵은 열림
    got = found(findings)
    assert (13, "basic") in got and (12, "secret") not in got


def test_asset_discovery():
    assets, findings, budget, target = run_engine(set())
    hosts = set(assets)
    assert {f"www.{DOMAIN}", f"api.{DOMAIN}", f"admin.{DOMAIN}", f"staging.{DOMAIN}",
            f"dev.{DOMAIN}", DOMAIN}.issubset(hosts)
    assert EXT_BUCKET in hosts          # #14 버킷을 자산으로 등록
    assert f"recruit.{DOMAIN}" in hosts  # #4 위탁 서비스(식별만)
    # 하위 도메인 찾기(#1)가 found_by에 들어간다
    assert 1 in assets[f"api.{DOMAIN}"].found_by


def test_all_fixed_no_findings():
    all_faults = {6, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 27, 28, 30, 31, 32}
    assets, findings, budget, target = run_engine(all_faults)
    assert found(findings) == set(), f"고친 상태인데 발견됨: {sorted(found(findings))}"


# ------------------------------------------------------------------ 안전·증거

def test_user_agent_and_get_only():
    _, _, _, target = run_engine(set())
    assert all(r.headers.get("user-agent") == USER_AGENT for r in target.requests)
    assert {r.method for r in target.requests} == {"GET"}


def test_evidence_masks_pii():
    _, findings, _, _ = run_engine(set())
    pii = next(f for f in findings if f.check_id == 16)
    assert "example.com" not in pii.evidence and "010-0000" not in pii.evidence
    assert "가림" in pii.evidence and len(pii.evidence) <= 200


def test_cve_attached_to_version_finding():
    _, findings, _, _ = run_engine(set())
    v = next(f for f in findings if f.check_id == 23)
    assert v.cves and v.cves[0]["id"] == "CVE-2021-41773" and v.cves[0]["kev"] is True


def test_no_double_findings_on_apex_and_www():
    _, findings, _, _ = run_engine(set())
    # #8은 대표 웹 자산 하나에서만 (꼭짓점·www 중복 없음)
    assert sum(1 for f in findings if f.check_id == 8) == 1
    # #18은 admin 하위 도메인에서 한 번만 (www/admin 경로와 중복 안 함)
    assert sum(1 for f in findings if f.check_id == 18) == 1


def test_demo_preset_findings():
    """기본 시연 프로필: #16·#8·#18만 결함. 크롤링이 robots → 사내 보고서 목록 → 내보내기 링크를 따라가
    www의 숨은 API(#16)도 찾는다. #16은 api·www 두 자산에서 한 건씩이다."""
    all_faults = {6, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 27, 28, 30, 31, 32}
    _, findings, _, _ = run_engine(all_faults - {16, 8, 18})
    assert found(findings) == {(8, "confirmed"), (16, "pii"), (18, "basic")}
    assert sorted(f.host for f in findings if f.check_id == 16) == [f"api.{DOMAIN}", f"www.{DOMAIN}"]


def test_hidden_export_found_by_following_links():
    _, findings, _, target = run_engine(set())
    www16 = next(f for f in findings if f.check_id == 16 and f.host == f"www.{DOMAIN}")
    assert "/internal/reports/export" in www16.location


def test_request_budget_capped():
    _, findings, budget, target = run_engine(set(), requests_limit=5)
    assert budget.requests_used <= 5 and len(target.requests) <= 5


def test_fixed_state_reports_safe_cert_and_headers():
    # #28·#30만 고치고 나머지 결함: 인증서·보안 헤더 발견이 사라진다
    assets, findings, _, _ = run_engine({28, 30})
    got = found(findings)
    assert not any(cid == 28 for cid, _ in got)
    assert not any(cid == 30 for cid, _ in got)
    assert (8, "confirmed") in got  # 다른 결함은 그대로


def test_test_server_discovered_when_open():
    assets, findings, _, _ = run_engine(set(), test_server=True)
    assert f"test.{DOMAIN}" in assets
    assert any(f.check_id == 19 and f.host == f"test.{DOMAIN}" for f in findings)


# ------------------------------------------------------------------ 서비스 통과(점검→점수→리포트)

def test_end_to_end_scan_through_service(tmp_path):
    """LiveEngine을 서비스에 끼워 HTTP 흐름으로 점검→점수→리포트까지 돈다(가짜 대상)."""
    from fastapi.testclient import TestClient

    from a2d.main import create_app
    from tests.test_api import EMAIL, ORIGIN, PASSWORD, login, setup_domain, wait_done

    client = httpx.AsyncClient(transport=httpx.MockTransport(FakeTarget(set())))
    s = Settings(admin_email=EMAIL, admin_password=PASSWORD, db_path=str(tmp_path / "a2d.sqlite3"),
                 web_origins=[ORIGIN])
    engine = LiveEngine(s, dns=FakeDns(set()), tls=FakeTls(set()), client=client, host_min_interval=0)

    with TestClient(create_app(s, engine=engine), base_url="http://testserver",
                    headers={"Origin": ORIGIN}) as c:
        login(c)
        domain_id = setup_domain(c)
        scan_id = c.post(f"/api/v1/domains/{domain_id}/scans").json()["scan_id"]
        done = wait_done(c, scan_id)
        assert done["status"] == "done", done

        findings = c.get(f"/api/v1/scans/{scan_id}/findings").json()["items"]
        checks = {f["check_id"] for f in findings}
        assert {8, 16, 18}.issubset(checks)  # 시연 핵심 결함을 실제로 찾았다

        summary = c.get(f"/api/v1/domains/{domain_id}/summary").json()
        assert summary["grade"] in ("F", "D", "C")  # 결함이 많아 낮은 등급
        assert 0 <= summary["safety_score"] < 90
        assert summary["today_tasks"], "오늘 할 일이 비어 있음"


def test_untrusted_issuer_reports_28(monkeypatch):
    """A2D_CA_BUNDLE로 체인을 검증해 믿을 수 없는 발급자(trusted=False)로 나오면 자체 서명이 아니어도 #28이다."""
    def untrusted(self, host, port=443):
        return CertInfo(not_after=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365),
                        self_signed=False, hostname_ok=True, trusted=False)

    monkeypatch.setattr(FakeTls, "inspect", untrusted)
    all_faults = {6, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 27, 28, 30, 31, 32}
    _, findings, _, _ = run_engine(all_faults)
    assert found(findings) == {(28, "invalid")}


def test_domain_expiry_from_rdap(monkeypatch):
    """#33: RDAP 만료일이 30일 안이면 expiring30, 9999년(공공기관)이면 보고하지 않는다."""
    all_faults = {6, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 27, 28, 30, 31, 32}
    soon = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=20)

    async def reg(http, domain):
        return {"expires": soon, "transfer_locked": False}
    monkeypatch.setattr(intel, "domain_registration", reg)
    _, findings, _, _ = run_engine(all_faults)
    f = next(f for f in findings if f.check_id == 33)
    assert f.situation == "expiring30" and "이전 잠금 꺼짐" in f.evidence

    async def public(http, domain):
        return {"expires": dt.datetime(9999, 12, 30, tzinfo=dt.timezone.utc), "transfer_locked": True}
    monkeypatch.setattr(intel, "domain_registration", public)
    _, findings, _, _ = run_engine(all_faults)
    assert not any(f.check_id == 33 for f in findings)
