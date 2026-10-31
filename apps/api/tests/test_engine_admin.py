"""관리자 로그인 화면(#18)을 '열려 있는 곳' 기준으로 한 번만 세는지 본다.

예전에는 admin 하위 도메인이 DNS에 '있기만' 하면 www의 관리자 경로를 건너뛰어, 하위 도메인은 막고
www/admin을 열어 둔 경우를 놓쳤다.
"""

import asyncio

import httpx

from a2d.config import Settings
from a2d.engine.base import Budget, EngineContext
from a2d.engine.live import LiveEngine
from tests.test_engine_live import ADMIN_LOGIN, DOMAIN, FakeDns, FakeTarget, FakeTls


def scan(transport, fixed=frozenset()):
    client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    engine = LiveEngine(Settings(), dns=FakeDns(set(fixed)), tls=FakeTls(set(fixed)), client=client,
                        host_min_interval=0)
    findings = []
    ctx = EngineContext("S", DOMAIN, 1, Budget(300, 20, 300), lambda *a: None, lambda a: "A",
                        lambda f: findings.append(f) or ("F", "A"), lambda *a, **k: None)
    asyncio.run(engine.run(ctx))
    asyncio.run(client.aclose())
    return [(f.host, f.location) for f in findings if f.check_id == 18]


def test_admin_subdomain_blocked_but_www_admin_open():
    target = FakeTarget(set())

    def handler(request):
        if request.url.host == f"admin.{DOMAIN}":
            return httpx.Response(403, text="blocked")
        return target(request)

    assert scan(handler) == [(f"www.{DOMAIN}", f"GET https://www.{DOMAIN}/admin")]


def test_both_open_counted_once_on_admin_subdomain():
    assert scan(FakeTarget(set())) == [(f"admin.{DOMAIN}", f"GET https://admin.{DOMAIN}/")]


def test_phpmyadmin_login_found():
    target = FakeTarget({18})  # /admin은 모두 막힘

    def handler(request):
        if request.url.host == f"www.{DOMAIN}" and request.url.path == "/phpmyadmin/":
            return httpx.Response(200, text=ADMIN_LOGIN, headers={"content-type": "text/html"})
        return target(request)

    assert scan(handler, fixed={18}) == [(f"www.{DOMAIN}", f"GET https://www.{DOMAIN}/phpmyadmin/")]
