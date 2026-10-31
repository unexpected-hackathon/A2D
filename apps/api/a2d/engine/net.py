"""점검 엔진이 대상에 닿는 통로: HTTP(GET), DNS 조회, TLS 인증서 확인.

모두 읽기 전용이다. 실제 구현은 대상에 요청을 보내고, 테스트는 같은 자리에 가짜를 끼운다.
공통 규칙(상세설계 4절·NFR-04):
- 모든 HTTP 요청에 A2D 점검임을 밝히는 User-Agent를 붙인다.
- GET만 보낸다. 요청마다 10초 제한, 대상 호스트당 초당 2건으로 속도를 제한한다.
- 요청을 보낼 때마다 Budget.requests_used를 올리고, 점검 1회 300건 상한을 넘으면 더 보내지 않는다.
- 요청 사이 Budget.check()로 중지 요청·제한 시간을 확인한다(ScanStopped는 그대로 올려 보낸다).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import ssl
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from .base import Budget

log = logging.getLogger("a2d.engine.net")

USER_AGENT = "A2D-Scanner/1.0 (+external-exposure check; read-only; https://github.com/unexpected-hackathon/A2D)"
REQUEST_TIMEOUT = 10.0
HOST_MIN_INTERVAL = 0.5  # 대상 호스트당 초당 2건
MAX_BODY_BYTES = 262144  # 응답을 받은 뒤 앞부분만 본다(개인정보 대량 적재·거대 응답 방지)


@dataclass
class Fetched:
    """HTTP 응답 요약. 본문은 앞부분(MAX_BODY_BYTES)만 담는다."""

    url: str
    status: int
    headers: dict[str, str]  # 소문자 키
    text: str
    scheme: str
    # 리다이렉트(Location)만 따로 본다. 본문은 따라가지 않는다.
    location: str | None = None
    # Set-Cookie는 쿠키마다 따로 둔다. headers에서는 여러 줄이 쉼표로 합쳐져 쿠키별 속성을 가를 수 없다.
    set_cookies: list[str] = field(default_factory=list)

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


@dataclass
class CertInfo:
    """TLS 인증서 요약(#28). error가 있으면 그 외 값은 의미 없다."""

    not_after: dt.datetime | None = None
    self_signed: bool = False
    hostname_ok: bool = True
    tls_version: str | None = None
    error: str | None = None


class Http(Protocol):
    async def get(self, url: str) -> Fetched | None: ...


class Dns(Protocol):
    def a(self, name: str) -> list[str]: ...
    def cname(self, name: str) -> str | None: ...
    def txt(self, name: str) -> list[str]: ...


class Tls(Protocol):
    def inspect(self, host: str, port: int = 443) -> CertInfo: ...


# ==================================================================== HTTP

class HttpClient:
    """httpx 기반 GET. 예산·속도 제한·User-Agent를 지키고, 연결 실패는 None으로 돌려준다."""

    def __init__(self, budget: Budget, client: httpx.AsyncClient, *,
                 host_min_interval: float = HOST_MIN_INTERVAL):
        self.budget = budget
        self.client = client
        self.host_min_interval = host_min_interval
        self._last_at: dict[str, float] = {}

    async def get(self, url: str, extra_headers: dict[str, str] | None = None) -> Fetched | None:
        self.budget.check()  # 중지 요청·제한 시간(ScanStopped)
        if self.budget.requests_used >= self.budget.requests_limit:
            log.info("요청 예산(%d건) 소진", self.budget.requests_limit)
            return None
        host = httpx.URL(url).host
        await self._throttle(host)
        self.budget.requests_used += 1
        headers = {"User-Agent": USER_AGENT, **(extra_headers or {})}
        try:
            r = await self.client.get(url, headers=headers,
                                      timeout=REQUEST_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError as e:
            log.info("요청 실패 %s: %s", url, type(e).__name__)
            return None
        body = r.content[:MAX_BODY_BYTES]
        try:
            text = body.decode(r.encoding or "utf-8", errors="replace")
        except (LookupError, ValueError):
            text = body.decode("utf-8", errors="replace")
        return Fetched(url=str(r.url), status=r.status_code,
                       headers={k.lower(): v for k, v in r.headers.items()},
                       text=text, scheme=httpx.URL(url).scheme,
                       location=r.headers.get("location"),
                       set_cookies=r.headers.get_list("set-cookie"))

    async def _throttle(self, host: str) -> None:
        if self.host_min_interval <= 0 or not host:
            return
        wait = self._last_at.get(host, 0.0) + self.host_min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_at[host] = time.monotonic()


def open_http_client(verify: bool | str = False) -> httpx.AsyncClient:
    """점검용 httpx 클라이언트. verify는 호출부(A2D_CA_BUNDLE)가 정한다.

    기본은 검증을 끈다. 외부 노출 점검은 자체 서명·만료 인증서를 쓰는 서버도 내용을 읽어야 하고
    (그런 서버가 바로 점검 대상이다), 인증서 유효성은 #28이 따로 본다(target/README "결함 상태의 TLS").
    운영자가 CA 묶음 경로를 넣으면 그 CA로 검증한다. 이때 자체 서명 대상은 내용 조회가 실패하고 #28만 남는다.
    """
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
                             follow_redirects=False, verify=verify)


# ==================================================================== DNS

class DnsResolver:
    """dnspython 기반 조회. 설정한 DNS 서버를 쓰고, 조회 실패는 빈 결과로 돌려준다."""

    def __init__(self, servers: list[str] | None = None, timeout: float = 3.0):
        import dns.resolver  # 지역 import: 테스트 가짜는 이 클래스를 안 쓴다

        self._resolver = dns.resolver.Resolver(configure=not servers)
        self._timeout = timeout
        if servers:
            addrs, port = [], 53
            for s in servers:
                host, _, p = s.partition(":")
                addrs.append(host.strip())
                if p:
                    port = int(p)
            self._resolver.nameservers = addrs
            self._resolver.port = port

    def _query(self, name: str, rdtype: str):
        import dns.resolver

        try:
            return self._resolver.resolve(name, rdtype, lifetime=self._timeout)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers,
                dns.exception.Timeout, dns.name.EmptyLabel):
            return None

    def a(self, name: str) -> list[str]:
        ans = self._query(name, "A")
        return [r.address for r in ans] if ans is not None else []

    def cname(self, name: str) -> str | None:
        ans = self._query(name, "CNAME")
        if ans is None:
            return None
        return str(ans[0].target).rstrip(".").lower()

    def txt(self, name: str) -> list[str]:
        ans = self._query(name, "TXT")
        if ans is None:
            return []
        out = []
        for r in ans:
            out.append(b"".join(r.strings).decode("utf-8", errors="replace"))
        return out


# ==================================================================== TLS

class TlsInspector:
    """표준 ssl로 인증서를 받아 만료·발급자·이름 일치를 본다. 실제 핸드셰이크 1회."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def inspect(self, host: str, port: int = 443) -> CertInfo:
        import socket

        ctx = ssl.create_default_context()
        ctx.check_hostname = False  # 이름 불일치도 '오류'가 아니라 정보로 보려고 직접 판정한다
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with socket.create_connection((host, port), timeout=self.timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ss:
                    der = ss.getpeercert(binary_form=True)
                    version = ss.version()
        except (OSError, ssl.SSLError) as e:
            return CertInfo(error=type(e).__name__)
        return _parse_cert(der, host, version)


def _parse_cert(der: bytes, host: str, version: str | None) -> CertInfo:
    from cryptography import x509

    try:
        cert = x509.load_der_x509_certificate(der)
    except ValueError:
        return CertInfo(error="인증서를 읽지 못함")
    not_after = cert.not_valid_after_utc
    self_signed = cert.issuer == cert.subject
    hostname_ok = _hostname_matches(cert, host)
    return CertInfo(not_after=not_after, self_signed=self_signed,
                    hostname_ok=hostname_ok, tls_version=version)


def _hostname_matches(cert, host: str) -> bool:
    from cryptography import x509
    from cryptography.x509.oid import ExtensionOID

    names: list[str] = []
    try:
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        names = san.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        pass
    host = host.lower()
    for n in names:
        n = n.lower()
        if n == host or (n.startswith("*.") and host.endswith(n[1:]) and host.count(".") == n.count(".")):
            return True
    return False
