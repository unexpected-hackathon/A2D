"""홈페이지 컴포넌트(#24)와 TLS 버전을 자산 정보에 기록하는지 본다(FR-02: 자산마다 CMS·라이브러리 이름과 버전 표시).

컴포넌트는 점수에 넣지 않는다. 인증서는 자산 찾기에서 한 번만 보고 #28이 그 결과를 다시 쓴다.
"""

import datetime as dt

import httpx
import pytest

from a2d.config import Settings
from a2d.engine.live import LiveEngine, _identify_components, _tls_label
from a2d.engine.net import CertInfo, Fetched
from tests.test_engine_live import DOMAIN, FakeDns, FakeTarget, found, run_engine


def _home(text, headers=None):
    return Fetched(url=f"https://www.{DOMAIN}/", status=200, headers={"content-type": "text/html", **(headers or {})},
                   text=text, scheme="https")


def test_primary_web_asset_lists_components():
    assets, _, _, _ = run_engine(set())
    comps = {c["name"]: c for c in assets[f"www.{DOMAIN}"].components}
    assert comps["jQuery"] == {"name": "jQuery", "version": "1.12.4", "eol": True}
    assert comps["JobNest CMS"] == {"name": "JobNest CMS", "version": "2.3", "eol": False}
    assert comps["Apache"]["version"] == "2.4.49"
    assert comps["PHP"] == {"name": "PHP", "version": "8.1.2", "eol": True}


def test_components_do_not_change_findings():
    """컴포넌트 식별은 점수 미반영: 시연 프로필은 그대로 세 건이다."""
    all_faults = {6, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 27, 28, 30, 31, 32}
    _, findings, _, _ = run_engine(all_faults - {16, 8, 18})
    assert found(findings) == {(8, "confirmed"), (16, "pii"), (18, "basic")}


@pytest.mark.parametrize("text, headers, expect", [
    ('<meta name="generator" content="WordPress 6.4.2"><link href="/wp-content/x.css">', {},
     [{"name": "WordPress", "version": "6.4.2", "eol": False}]),
    ('<script src="/_next/static/chunks/main.js"></script>', {"server": "nginx/1.18.0"},
     [{"name": "nginx", "version": "1.18.0", "eol": False}, {"name": "Next.js", "version": "", "eol": False}]),
    ('<script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js">', {},
     [{"name": "jQuery", "version": "3.7.1", "eol": False}]),
    ('<script>createClient("https://abcd.supabase.co", anon)</script>', {},
     [{"name": "Supabase", "version": "", "eol": False}]),
    ("<html>plain</html>", {}, []),
])
def test_identify_components(text, headers, expect):
    assert _identify_components(_home(text, headers)) == expect


def test_tls_label():
    assert _tls_label("TLSv1.3") == "TLS 1.3" and _tls_label("TLSv1.2") == "TLS 1.2" and _tls_label(None) is None


class CountingTls:
    def __init__(self):
        self.hosts = []

    def inspect(self, host, port=443):
        self.hosts.append(host)
        return CertInfo(not_after=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7), self_signed=True,
                        tls_version="TLSv1.3")


def test_tls_version_recorded_and_cert_checked_once_per_host():
    import asyncio

    from a2d.engine.base import Budget, EngineContext

    tls = CountingTls()
    client = httpx.AsyncClient(transport=httpx.MockTransport(FakeTarget(set())))
    engine = LiveEngine(Settings(), dns=FakeDns(set()), tls=tls, client=client, host_min_interval=0)
    assets, findings = {}, []

    def add_finding(f):
        findings.append(f)
        return "F", "A"

    ctx = EngineContext("S", DOMAIN, 1, Budget(300, 20, 300), lambda *a: None,
                        lambda a: assets.__setitem__(a.host, a) or "A", add_finding, lambda *a, **k: None)
    asyncio.run(engine.run(ctx))
    asyncio.run(client.aclose())

    assert assets[f"www.{DOMAIN}"].tls_version == "TLS 1.3"
    assert assets[f"api.{DOMAIN}"].tls_version == "TLS 1.3"
    assert assets[f"recruit.{DOMAIN}"].tls_version is None  # 외부 위탁 서비스는 연결하지 않는다
    assert len(tls.hosts) == len(set(tls.hosts))           # #28이 같은 호스트에 다시 연결하지 않는다
    assert any(f.check_id == 28 for f in findings)


def test_components_reach_asset_api(tmp_path):
    from fastapi.testclient import TestClient

    from a2d.main import create_app
    from tests.test_api import EMAIL, ORIGIN, PASSWORD, login, setup_domain, wait_done

    client = httpx.AsyncClient(transport=httpx.MockTransport(FakeTarget(set())))
    s = Settings(admin_email=EMAIL, admin_password=PASSWORD, db_path=str(tmp_path / "a2d.sqlite3"),
                 web_origins=[ORIGIN])
    engine = LiveEngine(s, dns=FakeDns(set()), tls=CountingTls(), client=client, host_min_interval=0)
    with TestClient(create_app(s, engine=engine), base_url="http://testserver", headers={"Origin": ORIGIN}) as c:
        login(c)
        domain_id = setup_domain(c)
        scan_id = c.post(f"/api/v1/domains/{domain_id}/scans").json()["scan_id"]
        assert wait_done(c, scan_id)["status"] == "done"
        items = c.get(f"/api/v1/scans/{scan_id}/assets").json()["items"]
        www = next(a for a in items if a["host"] == f"www.{DOMAIN}")
        assert {"name": "jQuery", "version": "1.12.4", "eol": True} in www["components"]
        assert www["tls_version"] == "TLS 1.3"
