"""Attack 에이전트의 점검 핸들러(상세설계 4절 "Python 함수 도구 목록").

가드 층(`tools.Guard`)이 허용·범위·예산을 거른 뒤, 통과한 호출만 이 핸들러에 넘긴다.
핸들러는 점검 대상에 '읽기(GET) 요청만' 보내고, 발견은 `ctx.add_finding`으로 저장소에 기록하며,
LLM에는 발견 ID·상태·마스킹된 증거만 돌려준다(응답 원문·위치·host 금지).

- probe_http: 자산 하나의 웹 응답을 다시 확인하고, 화면 코드·OpenAPI에서 조회 API 엔드포인트를
  찾아 Scope에 등록한다. 발견은 기록하지 않는다(버전·컴포넌트 식별과 점수는 기본 점검/점수 코드가 맡는다).
- check_unauth_api(#16): 찾은 조회 엔드포인트 하나를 인증 없이 한 번 호출해 개인정보 형태의 데이터가
  돌아오는지 본다. 돌아오면 발견을 기록하고, 아니면 "이상 없음"을 돌려준다.

안전 규칙(상세설계 4절·2.4, PRD NFR-04):
- 모든 요청에 A2D 점검임을 밝히는 User-Agent를 붙인다.
- GET만 보낸다(쓰기·변경 금지). 요청마다 10초 제한, 대상 호스트당 초당 2건으로 속도를 제한한다.
- 요청을 보낼 때마다 ctx.budget.requests_used를 올리고, 상한(0이면 없음)을 넘으면 더 보내지 않는다.
- 요청 사이사이 ctx.budget.check()로 중지 요청·제한 시간을 확인한다(ScanStopped는 그대로 올려 보낸다).
- 개인정보·비밀값은 마스킹된 발췌(200자 이내)만 근거로 저장하고, LLM에는 원문을 넘기지 않는다.

실제 연결 설정(TLS 검증·시연 CA·DNS)은 호출하는 쪽이 만든 httpx.AsyncClient에 담아 넘긴다.
이 모듈은 넘겨받은 클라이언트로 요청만 보낸다(테스트는 httpx.MockTransport를 끼운다).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx

from ..engine.base import EngineContext, RawFinding
from .tools import AssetArgs, Endpoint, EndpointArgs, Handler, Scope, ToolResult

log = logging.getLogger("a2d.agents.handlers")

# 모든 요청에 붙이는 식별 User-Agent(NFR-04, 상세설계 4절). 담당자가 로그에서 A2D 점검임을 알 수 있게 한다.
USER_AGENT = "A2D-Scanner/1.0 (+external-exposure check; read-only; https://github.com/unexpected-hackathon/A2D)"

REQUEST_TIMEOUT = 10.0  # 요청마다 10초 제한(상세설계 4절)
HOST_MIN_INTERVAL = 0.5  # 대상 호스트당 초당 2건
MAX_BODY_READ = 65536  # 응답을 받은 뒤 앞부분만 본다(개인정보 대량 적재 방지)
EVIDENCE_LIMIT = 200  # 마스킹된 증거 길이 상한(NFR-05)

# 개인정보 형태 판별(값은 저장하지 않고 '있다'만 센다)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# 숫자 경계: 주문번호·타임스탬프가 전화번호·주민번호로 잘못 잡히지 않게 앞뒤를 본다.
_PHONE = re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
_RRN = re.compile(r"(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)")  # 주민등록번호 형태
# 개인정보 성격의 필드 이름(응답이 JSON일 때). 값이 아니라 키만 본다.
_PII_KEYS = {"email", "phone", "mobile", "tel", "name", "username", "birth", "birthday",
             "rrn", "ssn", "resident", "address", "resume", "applicant"}

# OpenAPI나 화면 코드에서 뽑을 API 경로 형태. 쿼리·조각은 Scope.add_endpoint가 떼어 낸다.
_API_PATH = re.compile(r"""["'(]\s*(/(?:api|v\d)[A-Za-z0-9/_.\-{}:]*)""")


class AttackProbe:
    """점검 1회의 Attack 핸들러 묶음. ctx와 httpx 클라이언트를 들고, 호스트별 속도 제한 상태를 유지한다."""

    def __init__(self, ctx: EngineContext, client: httpx.AsyncClient, *,
                 scheme: str = "https", host_min_interval: float = HOST_MIN_INTERVAL):
        self.ctx = ctx
        self.client = client
        self.scheme = scheme
        self.host_min_interval = host_min_interval
        self._last_at: dict[str, float] = {}

    # ---------------------------------------------------------------- 등록표

    @property
    def handlers(self) -> dict[str, Handler]:
        """Guard에 끼울 {도구 이름: 핸들러}. 가드가 이 표에 있는 도구만 LLM에 보여 준다."""
        return {"probe_http": self._probe_http, "check_unauth_api": self._check_unauth_api}

    # ---------------------------------------------------------------- 공용 요청

    async def _get(self, host: str, path: str) -> httpx.Response | None:
        """GET 한 번. 예산을 넘었으면 None, 연결 실패도 None. ScanStopped는 올려 보낸다."""
        self.ctx.budget.check()  # 중지 요청·제한 시간
        b = self.ctx.budget
        if b.requests_exhausted:
            log.info("요청 예산(%d건) 소진으로 추가 요청 안 함", b.requests_limit)
            return None
        await self._throttle(host)
        b.requests_used += 1
        url = f"{self.scheme}://{host}{path}"
        try:
            # 읽기 전용: GET만. 리다이렉트는 따라가지 않는다(다른 호스트로 새지 않게).
            r = await self.client.get(url, headers={"User-Agent": USER_AGENT},
                                      timeout=REQUEST_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError as e:
            log.info("요청 실패 %s: %s", path, type(e).__name__)
            return None
        return r

    async def _throttle(self, host: str) -> None:
        if self.host_min_interval <= 0:
            return
        now = time.monotonic()
        wait = self._last_at.get(host, 0.0) + self.host_min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_at[host] = time.monotonic()

    # ---------------------------------------------------------------- probe_http

    async def _probe_http(self, args: AssetArgs, scope: Scope) -> ToolResult:
        """자산 하나의 웹 응답을 다시 확인하고 조회 API 엔드포인트를 찾아 Scope에 등록한다."""
        asset = scope.assets[args.asset_id]  # Guard가 범위를 이미 확인했다
        host = asset.host
        root = await self._get(host, "/")
        if root is None:
            return ToolResult({"status": "unreachable", "asset_id": args.asset_id},
                              f"{asset.alias} 응답 없음")
        headers = self._safe_headers(root)
        product = self._guess_product(root, headers)

        # 화면 코드(JS 포함 HTML)와 OpenAPI 문서에서 조회 경로 후보를 모은다.
        paths = self._paths_from_body(root)
        openapi = await self._get(host, "/openapi.json")
        if openapi is not None and openapi.status_code == 200:
            paths |= self._paths_from_openapi(openapi)

        found: list[dict] = []
        for method, path in sorted(paths):
            e = scope.add_endpoint(args.asset_id, method, path)
            if e is not None:
                found.append({"endpoint_id": e.endpoint_id, "method": e.method,
                              "path": e.path, "callable": e.callable})
        data = {
            "status": "ok",
            "asset_id": args.asset_id,
            "http_status": root.status_code,
            "headers": headers,          # server·x-powered-by 등 안전한 헤더만
            "product_guess": product,    # #24 식별 힌트(점수에는 반영하지 않음)
            "endpoints": found,          # 조회 엔드포인트 ID(경로는 Scope가 정제한 값)
        }
        callable_n = sum(1 for e in found if e["callable"])
        return ToolResult(data, f"HTTP {root.status_code}, 엔드포인트 {len(found)}개(호출 가능 {callable_n})")

    @staticmethod
    def _safe_headers(r: httpx.Response) -> dict:
        """LLM에 보내도 되는 헤더만 고른다. 쿠키·set-cookie 등 민감한 값은 뺀다."""
        keep = ("server", "x-powered-by", "content-type", "x-frame-options",
                "strict-transport-security", "content-security-policy")
        return {k: r.headers[k][:120] for k in keep if k in r.headers}

    @staticmethod
    def _guess_product(r: httpx.Response, headers: dict) -> list[str]:
        out = []
        for k in ("server", "x-powered-by"):
            if headers.get(k):
                out.append(headers[k])
        m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']{1,60})',
                      r.text[:MAX_BODY_READ], re.I)
        if m:
            out.append(m.group(1).strip())
        return out

    @classmethod
    def _paths_from_body(cls, r: httpx.Response) -> set[tuple[str, str]]:
        ct = r.headers.get("content-type", "")
        if not ("html" in ct or "javascript" in ct or "json" in ct):
            return set()
        return {("GET", m.group(1)) for m in _API_PATH.finditer(r.text[:MAX_BODY_READ])}

    @staticmethod
    def _paths_from_openapi(r: httpx.Response) -> set[tuple[str, str]]:
        try:
            spec = r.json()
        except (ValueError, json.JSONDecodeError):
            return set()
        if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
            return set()
        out: set[tuple[str, str]] = set()
        for path, ops in spec["paths"].items():
            if not isinstance(path, str) or not isinstance(ops, dict):
                continue
            for method in ops:
                if isinstance(method, str) and method.upper() == "GET":
                    out.add(("GET", path))
        return out

    # ---------------------------------------------------------------- check_unauth_api (#16)

    async def _check_unauth_api(self, args: EndpointArgs, scope: Scope) -> ToolResult:
        """조회 엔드포인트 하나를 인증 없이 호출해 개인정보 형태 데이터가 오는지 본다(#16)."""
        asset = scope.assets[args.asset_id]
        endpoint: Endpoint = scope.endpoints[args.endpoint_id]  # Guard가 호출 가능 여부를 확인했다
        r = await self._get(asset.host, endpoint.path)
        if r is None:
            return ToolResult({"status": "error", "reason": "요청을 보내지 못함"}, "요청 실패")

        location = f"GET {self.scheme}://{asset.host}{endpoint.path}"  # 저장만 하고 LLM엔 보내지 않는다
        if r.status_code in (401, 403):
            return ToolResult({"status": "clean", "endpoint_id": args.endpoint_id, "http_status": r.status_code},
                              f"인증 필요({r.status_code}), 이상 없음")
        if r.status_code != 200:
            return ToolResult({"status": "clean", "endpoint_id": args.endpoint_id, "http_status": r.status_code},
                              f"HTTP {r.status_code}, 개인정보 노출 없음")

        kinds, count = self._pii_shape(r)
        if not kinds:
            evidence = f"{r.status_code} 응답, 개인정보 형태 아님"
            return ToolResult({"status": "clean", "endpoint_id": args.endpoint_id, "http_status": r.status_code},
                              evidence)

        evidence = self._mask_evidence(r.status_code, kinds, count)
        finding = RawFinding(host=asset.host, check_id=16, situation="pii",
                             location=location, evidence=evidence)
        finding_id, _asset_id = self.ctx.add_finding(finding)
        data = {"status": "finding", "finding_id": finding_id, "check_id": 16,
                "confidence": "확인됨", "evidence": evidence}
        return ToolResult(data, f"개인정보 형태 데이터 반환(발견 {finding_id})")

    @classmethod
    def _pii_shape(cls, r: httpx.Response) -> tuple[list[str], int | None]:
        """응답이 개인정보 형태인지(JSON만). (검출한 종류, 항목 수). 값 자체는 남기지 않는다.

        #16은 확인됨·C=5라 오탐 비용이 가장 크다. JSON 응답만 보고(HTML 푸터 메일 제외),
        개인정보 필드가 있거나 값 형태가 2종 이상일 때만 pii로 본다. 값 하나로는 켜지 않는다.
        """
        ct = r.headers.get("content-type", "")
        if "json" not in ct:
            return [], None
        try:
            obj = r.json()
        except (ValueError, json.JSONDecodeError):
            return [], None
        body = r.text[:MAX_BODY_READ]
        value_kinds: list[str] = []
        if _EMAIL.search(body):
            value_kinds.append("이메일")
        if _PHONE.search(body):
            value_kinds.append("전화번호")
        if _RRN.search(body):
            value_kinds.append("주민등록번호")

        items = cls._items_of(obj)
        count = len(items) if items is not None else None
        has_field = False
        if items is not None:
            keys = {str(k).lower() for it in items[:5] if isinstance(it, dict) for k in it}
            has_field = bool(keys & _PII_KEYS)
        if not (has_field or len(value_kinds) >= 2):
            return [], count
        return value_kinds + (["개인정보 필드"] if has_field else []), count

    @staticmethod
    def _items_of(obj: Any) -> list | None:
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for key in ("items", "data", "results", "list"):
                if isinstance(obj.get(key), list):
                    return obj[key]
            # 단일 객체도 1건으로 본다
            return [obj]
        return None

    @staticmethod
    def _mask_evidence(status: int, kinds: list[str], count: int | None) -> str:
        where = f"{count}건" if count is not None else "데이터"
        text = f"{status} 응답, {where}에 {'·'.join(kinds)} 형식 포함(마스킹)"
        return text[:EVIDENCE_LIMIT]


def build_attack_handlers(ctx: EngineContext, client: httpx.AsyncClient, *,
                          scheme: str = "https", host_min_interval: float = HOST_MIN_INTERVAL
                          ) -> dict[str, Handler]:
    """run_attack에 넘길 Attack 핸들러 표를 만든다. client는 호출하는 쪽이 수명·TLS 설정을 관리한다."""
    return AttackProbe(ctx, client, scheme=scheme, host_min_interval=host_min_interval).handlers


def open_client(resolve=None) -> httpx.AsyncClient:
    """점검용 httpx 클라이언트. 읽기 전용·식별 User-Agent·리다이렉트 비추적, 인증서는 검증하지 않는다.

    외부 노출 점검은 자체 서명·만료 인증서를 쓰는 서버도 내용을 읽어야 하고(그런 서버가 점검 대상이다),
    인증서 유효성은 #28이 따로 본다(target/README "결함 상태의 TLS", engine.net.open_http_client).
    resolve(점검 DNS)를 주면 엔진과 같은 DNS로 접속 주소를 찾는다.
    """
    from ..engine.net import open_http_client

    return open_http_client(resolve=resolve)
