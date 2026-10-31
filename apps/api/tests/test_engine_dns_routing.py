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


# ------------------------------------------------------------------ A2D_CA_BUNDLE과 TLS 검증

def _tls_server(tmp_path, *, ca_signed: bool):
    """루프백 HTTPS 서버. ca_signed면 시험용 CA가 발급한 인증서, 아니면 자체 서명. (서버, 포트, CA 경로)"""
    import datetime as dt
    import ssl

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    def name(cn):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])

    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = (x509.CertificateBuilder().subject_name(name("A2D test CA")).issuer_name(name("A2D test CA"))
          .public_key(ca_key.public_key()).serial_number(1).not_valid_before(now - dt.timedelta(days=1))
          .not_valid_after(now + dt.timedelta(days=365))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    builder = (x509.CertificateBuilder().subject_name(name(NAME)).public_key(key.public_key()).serial_number(2)
               .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(NAME)]), critical=False))
    cert = (builder.issuer_name(name("A2D test CA")).sign(ca_key, hashes.SHA256()) if ca_signed
            else builder.issuer_name(name(NAME)).sign(key, hashes.SHA256()))

    pem = serialization.Encoding.PEM
    (tmp_path / "ca.crt").write_bytes(ca.public_bytes(pem))
    (tmp_path / "srv.crt").write_bytes(cert.public_bytes(pem))
    (tmp_path / "srv.key").write_bytes(key.private_bytes(pem, serialization.PrivateFormat.PKCS8,
                                                         serialization.NoEncryption()))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(tmp_path / "srv.crt", tmp_path / "srv.key")
    server.socket = sctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1], str(tmp_path / "ca.crt")


def loopback(host):
    return ["127.0.0.1"] if host == NAME else []


def test_ca_bundle_marks_untrusted_cert_for_28(tmp_path):
    for ca_signed, trusted in ((True, True), (False, False)):
        d = tmp_path / str(ca_signed)
        d.mkdir()
        server, port, ca = _tls_server(d, ca_signed=ca_signed)
        try:
            with_ca = TlsInspector(resolve=loopback, ca_bundle=ca).inspect(NAME, port)
            without = TlsInspector(resolve=loopback).inspect(NAME, port)
        finally:
            server.shutdown()
        assert with_ca.error is None and with_ca.trusted is trusted
        assert with_ca.self_signed is (not ca_signed)
        assert without.trusted is None  # CA 묶음이 없으면 판정하지 않는다(예전 동작 그대로)


def test_content_fetch_reads_self_signed_target(tmp_path):
    """자체 서명 대상도 내용을 읽는다. 예전에는 A2D_CA_BUNDLE을 넣으면 모든 요청이 실패해 점검이 '연결 실패'로 끝났다."""
    server, port, _ = _tls_server(tmp_path, ca_signed=False)
    try:
        async def go():
            async with open_http_client(resolve=loopback) as c:
                return await HttpClient(Budget(10, 1, 60), c, host_min_interval=0).get(f"https://{NAME}:{port}/")

        r = asyncio.run(go())
    finally:
        server.shutdown()
    assert r is not None and r.status == 200 and r.text == "ok"


def test_engine_uses_ca_bundle_only_for_tls_inspector(tmp_path):
    server, _, ca = _tls_server(tmp_path, ca_signed=True)
    server.shutdown()
    eng = LiveEngine(Settings(ca_bundle=ca))
    assert eng._tls._verify_ctx is not None
    assert LiveEngine(Settings())._tls._verify_ctx is None
