"""모르는 경로에도 200 index.html을 주는 SPA에서 경로 점검(#9·#18·#20)이 오탐하지 않는지 본다.

바이브코딩으로 만든 앱은 대부분 이렇게 배포된다. 문제가 없는 SPA는 발견이 0건이어야 하고,
같은 SPA에 실제 파일이 열려 있으면 그것은 찾아야 한다.
"""

import asyncio
import datetime as dt
import json

import httpx
import pytest

from a2d.config import Settings
from a2d.engine.base import Budget, EngineContext
from a2d.engine.live import LiveEngine, _config_file_matches, _status_page_matches
from a2d.engine.net import CertInfo, Fetched
from tests.test_engine_live import found, run_engine

DOMAIN = "shop.example"
INDEX = ('<!doctype html><html><head><title>My Shop</title></head><body><div id="root"></div>'
         '<script type="module" src="/assets/index-3f2a.js"></script></body></html>')
SAFE_HEADERS = {"strict-transport-security": "max-age=31536000", "content-security-policy": "default-src 'self'",
                "x-frame-options": "DENY"}


class FakeSpa:
    """흔한 SPA 배포: HTTP는 HTTPS로 옮기고, 모르는 경로는 200 index.html. exposed는 실제로 열린 파일."""

    def __init__(self, exposed: dict[str, tuple[str, str]] | None = None, echo_path=False):
        self.exposed = exposed or {}
        self.echo_path = echo_path

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.scheme == "http":
            return httpx.Response(301, headers={"location": f"https://{request.url.host}{path}"})
        if path in self.exposed:
            body, media = self.exposed[path]
            return httpx.Response(200, text=body, headers={**SAFE_HEADERS, "content-type": media})
        if path.endswith(".js"):
            return httpx.Response(200, text="console.log('app')",
                                  headers={**SAFE_HEADERS, "content-type": "application/javascript"})
        body = INDEX.replace("</body>", f"<!-- {path} --></body>") if self.echo_path else INDEX
        return httpx.Response(200, text=body, headers={**SAFE_HEADERS, "content-type": "text/html"})


class SpaDns:
    def a(self, name):
        return ["203.0.113.10"] if name in (DOMAIN, f"www.{DOMAIN}") else []

    def cname(self, name):
        return None

    def txt(self, name):
        if name == DOMAIN:
            return ["v=spf1 include:_spf.example -all"]
        if name == f"_dmarc.{DOMAIN}":
            return ["v=DMARC1; p=reject"]
        return []


class SafeTls:
    def inspect(self, host, port=443):
        return CertInfo(not_after=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=200))


def scan_spa(target: FakeSpa):
    client = httpx.AsyncClient(transport=httpx.MockTransport(target))
    engine = LiveEngine(Settings(), dns=SpaDns(), tls=SafeTls(), client=client, host_min_interval=0)
    assets, findings = {}, []

    def add_asset(a):
        assets[a.host] = a
        return f"A-{len(assets):03d}"

    def add_finding(f):
        f.validate()
        findings.append(f)
        return f"F-{len(findings):04d}", "A-001"

    ctx = EngineContext("S-1", DOMAIN, 1, Budget(300, 20, 300), lambda *a: None, add_asset, add_finding,
                        lambda *a, **k: None)
    asyncio.run(engine.run(ctx))
    asyncio.run(client.aclose())
    return findings


@pytest.mark.parametrize("echo_path", [False, True])
def test_clean_spa_has_no_findings(echo_path):
    findings = scan_spa(FakeSpa(echo_path=echo_path))
    assert found(findings) == set(), [(f.check_id, f.situation, f.location) for f in findings]


def test_spa_with_real_exposed_files_still_found():
    findings = scan_spa(FakeSpa({
        "/.env": ("DB_PASSWORD=hunter2\nAPI_KEY=abc\n", "text/plain"),
        "/actuator/env": (json.dumps({"activeProfiles": ["prod"], "propertySources": []}), "application/json"),
    }))
    assert found(findings) == {(9, "env"), (20, "env")}


def test_git_repository_reported_once():
    _, findings, _, _ = run_engine(set())
    assert [f.situation for f in findings if f.check_id == 9].count("git") == 1


def _r(text, ctype="text/plain"):
    return Fetched(url="https://www.shop.example/x", status=200, headers={"content-type": ctype},
                   text=text, scheme="https")


@pytest.mark.parametrize("path, text, ctype, ok", [
    ("/.env", "# comment\nDB_HOST=10.0.0.1\n", "text/plain", True),
    ("/.env", "export SECRET_KEY=abc", "text/plain", True),
    ("/.env", INDEX, "text/html", False),
    ("/.env", "Not Found", "text/plain", False),
    ("/.git/HEAD", "ref: refs/heads/main\n", "text/plain", True),
    ("/.git/HEAD", "a" * 40 + "\n", "text/plain", True),
    ("/.git/HEAD", "hello", "text/plain", False),
    ("/.git/config", "[core]\n\tbare = false\n", "text/plain", True),
    ("/.git/config", INDEX, "application/octet-stream", False),  # 형식이 틀려도 HTML 본문이면 거른다
])
def test_config_file_matches(path, text, ctype, ok):
    assert _config_file_matches(path, _r(text, ctype)) is ok


@pytest.mark.parametrize("path, text, ctype, ok", [
    ("/actuator/env", json.dumps({"propertySources": []}), "application/json", True),
    ("/actuator/env", json.dumps({"status": "UP"}), "application/json", False),
    ("/server-status", "<h1>Apache Server Status for x</h1>", "text/html", True),
    ("/server-status", INDEX, "text/html", False),
    ("/phpinfo.php", "<title>phpinfo()</title><td>PHP Version 8.1.2</td>", "text/html", True),
    ("/metrics", "# HELP http_requests_total x\n# TYPE http_requests_total counter\n", "text/plain", True),
    ("/metrics", INDEX, "text/html", False),
])
def test_status_page_matches(path, text, ctype, ok):
    assert _status_page_matches(path, _r(text, ctype)) is ok
