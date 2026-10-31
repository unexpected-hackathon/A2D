"""점검이 대상에 닿지 못했을 때 '문제 없음(100점 A)'이 아니라 실패로 끝나는지 본다.

발견 0건은 100점이라, DNS 무응답·연결 불가를 조용히 넘기면 아무것도 못 본 점검이 A등급이 된다.
DNS가 답하지 않는 것(시간 초과)과 레코드가 없는 것(NXDOMAIN)도 구분해, 메일 사칭(#32)을 오탐하지 않는다.
"""

import asyncio

import httpx
import pytest

from a2d.config import Settings
from a2d.engine.base import Budget, EngineContext, EngineError
from a2d.engine.live import LiveEngine
from a2d.engine.net import DnsResolver, DnsUnavailable
from tests.test_engine_live import DOMAIN, FakeDns, FakeTarget, FakeTls, found


class DeadDns:
    """DNS 서버가 답하지 않는다(시연 DNS가 꺼졌거나 막힘)."""

    def __init__(self):
        self.calls = 0

    def _fail(self, name):
        self.calls += 1
        raise DnsUnavailable(f"{name}: Timeout")

    a = cname = txt = _fail


class TxtDeadDns(FakeDns):
    """주소 조회는 되는데 TXT 조회만 시간 초과."""

    def txt(self, name):
        raise DnsUnavailable(f"{name} TXT: Timeout")


class EmptyDns:
    def a(self, name):
        return []

    def cname(self, name):
        return None

    def txt(self, name):
        return []


def refuse(request):
    raise httpx.ConnectError("connection refused", request=request)


def run(dns, transport, fixed=frozenset()):
    client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    engine = LiveEngine(Settings(), dns=dns, tls=FakeTls(set(fixed)), client=client, host_min_interval=0)
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
    try:
        asyncio.run(engine.run(ctx))
    finally:
        asyncio.run(client.aclose())
    return assets, findings


def test_dns_down_fails_fast_instead_of_clean_result():
    dns = DeadDns()
    with pytest.raises(EngineError, match="DNS"):
        run(dns, FakeTarget(set()))
    assert dns.calls <= 3  # 시간 초과를 38번 쌓지 않고 바로 그만둔다


def test_no_hosts_fails():
    with pytest.raises(EngineError, match="호스트를 찾지 못해"):
        run(EmptyDns(), refuse)  # 주소가 없으니 홈페이지도 열리지 않는다


def test_unreachable_target_fails():
    with pytest.raises(EngineError, match="연결하지 못해"):
        run(FakeDns(set()), refuse)


def test_api_only_domain_is_not_treated_as_unreachable():
    """홈페이지가 없어도 다른 자산이 응답하면 점검을 이어 간다."""

    class ApiOnlyDns(EmptyDns):
        def a(self, name):
            return ["10.0.0.1"] if name == f"api.{DOMAIN}" else []

    def api_only(request):
        if request.url.host != f"api.{DOMAIN}":
            raise httpx.ConnectError("no route", request=request)
        return FakeTarget(set())(request)

    assets, findings = run(ApiOnlyDns(), api_only)
    assert set(assets) == {f"api.{DOMAIN}"}
    assert (16, "pii") in found(findings)


def test_txt_timeout_does_not_report_missing_spf_dmarc():
    _, findings = run(TxtDeadDns(set()), FakeTarget(set()))
    got = found(findings)
    assert not any(cid == 32 for cid, _ in got)
    assert (8, "confirmed") in got  # 나머지 점검은 그대로


def test_resolver_distinguishes_timeout_from_nxdomain(monkeypatch):
    import dns.exception
    import dns.resolver

    r = DnsResolver(["192.0.2.53"], timeout=0.1)

    def nx(name, rdtype, lifetime):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(r._resolver, "resolve", nx)
    assert r.a("nope.example") == [] and r.cname("nope.example") is None and r.txt("nope.example") == []

    def timeout(name, rdtype, lifetime):
        raise dns.exception.Timeout()

    monkeypatch.setattr(r._resolver, "resolve", timeout)
    with pytest.raises(DnsUnavailable):
        r.txt("example.com")


def test_failed_scan_shows_reason_through_service(tmp_path):
    """서비스를 거치면 점검은 failed가 되고, 이유가 error_message로 보이며 점수는 생기지 않는다."""
    from fastapi.testclient import TestClient

    from a2d.main import create_app
    from tests.test_api import EMAIL, ORIGIN, PASSWORD, login, setup_domain, wait_done

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    s = Settings(admin_email=EMAIL, admin_password=PASSWORD, db_path=str(tmp_path / "a2d.sqlite3"),
                 web_origins=[ORIGIN], verify_mode="trust", fixture_step_sec=0)
    engine = LiveEngine(s, dns=FakeDns(set()), tls=FakeTls(set()), client=client, host_min_interval=0)

    with TestClient(create_app(s, engine=engine), base_url="http://testserver",
                    headers={"Origin": ORIGIN}) as c:
        login(c)
        domain_id = setup_domain(c)
        scan_id = c.post(f"/api/v1/domains/{domain_id}/scans").json()["scan_id"]
        done = wait_done(c, scan_id)
        assert done["status"] == "failed", done
        assert "연결하지 못해" in done["error_message"]
        assert done.get("safety_score") is None
