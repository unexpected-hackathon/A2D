"""점검 DNS(A2D_DNS_SERVER)를 정했을 때 HTTP·TLS 접속도 그 DNS로 주소를 찾는지 본다.

예전에는 자산은 점검 DNS로 찾고 접속은 시스템 DNS로 해서, 노트북에서 직접 띄우면 시연 대상에 닿지 못하고
자산 몇 개와 #32만 남는(D등급) 결과가 경고 없이 나왔다.
"""

import asyncio
import http.server
import threading

import httpx

from a2d.config import Settings
from a2d.engine.base import Budget
from a2d.engine.live import LiveEngine
from a2d.engine.net import DnsPinnedTransport, HttpClient, TlsInspector, open_http_client

NAME = "www.jobnest.test"
ADDR = "10.253.53.80"


def resolve(host):
    return [ADDR] if host == NAME else []


def pinned_client(inner_handler):
    seen = []

    def handler(request):
        seen.append(request)
        return inner_handler(request)

    transport = DnsPinnedTransport(resolve, httpx.MockTransport(handler))
    return httpx.AsyncClient(transport=transport), seen


def test_pinned_transport_connects_to_resolved_address_with_original_name():
    client, seen = pinned_client(lambda r: httpx.Response(200, text="ok"))

    async def go():
        async with client:
            return await HttpClient(Budget(10, 1, 60), client, host_min_interval=0).get(f"https://{NAME}/robots.txt")

    r = asyncio.run(go())
    inner = seen[0]
    assert inner.url.host == ADDR and inner.url.path == "/robots.txt"
    assert inner.headers["host"] == NAME                 # 가상 호스트는 원래 이름으로 고른다
    assert inner.extensions["sni_hostname"] == NAME      # TLS 이름(SNI)도 원래 이름
    assert r.status == 200 and r.url == f"https://{NAME}/robots.txt"  # 발견 위치에는 이름이 남는다


def test_unresolvable_or_dns_error_is_connection_failure():
    client, seen = pinned_client(lambda r: httpx.Response(200))

    def broken(host):
        raise TimeoutError("dns down")

    async def go():
        async with client:
            http = HttpClient(Budget(10, 1, 60), client, host_min_interval=0)
            missing = await http.get("https://nope.jobnest.test/")
        async with httpx.AsyncClient(transport=DnsPinnedTransport(broken, httpx.MockTransport(
                lambda r: httpx.Response(200)))) as c2:
            down = await HttpClient(Budget(10, 1, 60), c2, host_min_interval=0).get(f"https://{NAME}/")
        return missing, down

    missing, down = asyncio.run(go())
    assert missing is None and down is None and seen == []


def test_tls_inspector_uses_resolved_address(monkeypatch):
    import socket

    calls = []

    def fake_connect(address, timeout=None):
        calls.append(address)
        raise OSError("refused")

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    info = TlsInspector(resolve=resolve).inspect(NAME)
    assert calls == [(ADDR, 443)] and info.error
    assert TlsInspector(resolve=resolve).inspect("nope.jobnest.test").error  # 주소가 없으면 연결하지 않는다
    assert len(calls) == 1


def test_engine_wires_scan_dns_into_http_and_tls():
    eng = LiveEngine(Settings(dns_servers=["127.0.0.1:15353"]))
    assert eng._resolve is not None and eng._tls._resolve == eng._resolve
    assert LiveEngine(Settings())._resolve is None  # 점검 DNS가 없으면 시스템 DNS 그대로


def test_open_http_client_reaches_server_through_pinned_address():
    """실제 전송 계층으로: 이름은 시스템 DNS에 없지만 점검 DNS가 준 주소(루프백)로 닿는다."""
    hosts = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hosts.append(self.headers["Host"])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        async def go():
            async with open_http_client(resolve=lambda h: ["127.0.0.1"] if h == "shop.invalid" else []) as c:
                return await HttpClient(Budget(10, 1, 60), c, host_min_interval=0).get(
                    f"http://shop.invalid:{port}/")

        r = asyncio.run(go())
    finally:
        server.shutdown()
    assert r is not None and r.status == 200 and r.text == "ok"
    assert hosts == [f"shop.invalid:{port}"]
