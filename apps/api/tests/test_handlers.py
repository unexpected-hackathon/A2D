"""Attack 점검 핸들러(probe_http·check_unauth_api)를 가짜 대상 서버로 확인한다.

httpx.MockTransport로 시연 대상(JobNest)의 응답을 흉내 낸다. 실제 네트워크는 쓰지 않는다.
읽기 전용·User-Agent·요청 예산·속도 제한·증거 가림·발견 기록을 확인한다.
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from a2d.agents.handlers import USER_AGENT, AttackProbe, build_attack_handlers
from a2d.agents.tools import Guard, Scope
from a2d.engine.base import Budget, RawFinding, ScanStopped


def _resp(text, ctype="application/json"):
    return httpx.Response(200, text=text, headers={"content-type": ctype})


@pytest.mark.parametrize("text, ctype", [
    (json.dumps({"order_id": "2024010123456789"}), "application/json"),  # 주문번호가 전화번호로 안 잡힘
    (json.dumps({"ts": 1701012345678}), "application/json"),            # 타임스탬프
    ("<footer>support@jobnest.test</footer>", "text/html"),             # HTML 푸터 메일
    (json.dumps({"items": [{"id": 1, "title": "백엔드"}]}), "application/json"),  # 개인정보 아님
    (json.dumps({"contact": "support@jobnest.test"}), "application/json"),  # 메일 하나(1종, 필드 없음)
])
def test_pii_shape_no_false_positive(text, ctype):
    kinds, _ = AttackProbe._pii_shape(_resp(text, ctype))
    assert kinds == [], f"오탐: {kinds}"


def test_pii_shape_detects_real_pii():
    body = json.dumps({"total": 40, "items": [
        {"id": 1, "name": "김민준", "email": "a@example.com", "phone": "010-0000-0001"}]})
    kinds, count = AttackProbe._pii_shape(_resp(body))
    assert "개인정보 필드" in kinds and count == 1

SUMMARY = {
    "assets": [
        {"asset_id": "A-001", "host": "www.jobnest.test", "alias": "www", "tags": ["web"], "importance": 4},
        {"asset_id": "A-002", "host": "api.jobnest.test", "alias": "api", "tags": ["api"], "importance": 5},
    ],
    "findings": [{"asset_id": "A-002", "check_id": 16, "situation": "개인정보 형태 데이터 반환"}],
}

# 가짜 지원자 데이터(개인정보 형태). 값은 모두 가짜다.
APPLICANTS = {"page": 1, "total": 40, "items": [
    {"id": 1, "name": "김민준", "email": "applicant001@example.com", "phone": "010-0000-0001"},
    {"id": 2, "name": "이서연", "email": "applicant002@example.com", "phone": "010-0000-0002"},
]}

WWW_APP_JS = b"""
var JN_CONFIG = { apiBase: "https://api.jobnest.test" };
fetch(JN_CONFIG.apiBase + "/api/v1/jobs");
fetch(JN_CONFIG.apiBase + "/api/v1/applicants?page=1");
fetch("/api/v1/resumes/presign");
"""

API_OPENAPI = {"openapi": "3.0.0", "paths": {
    "/api/v1/jobs": {"get": {}},
    "/api/v1/applicants": {"get": {}, "post": {}},
    "/api/v1/applicants/{applicant_id}": {"get": {}},
    "/api/v1/status": {"get": {}},
}}


def target(responses):
    """경로 → (status, headers, body). body는 bytes/str/dict. 기록을 위해 요청을 모은다."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        key = f"{request.url.host}{request.url.path}"
        spec = responses.get(key)
        if spec is None:
            return httpx.Response(404, text="not found")
        status, headers, body = spec
        if isinstance(body, dict):
            return httpx.Response(status, json=body, headers=headers)
        if isinstance(body, str):
            body = body.encode()
        return httpx.Response(status, content=body, headers=headers)

    return handler, seen


def make(responses, *, requests_limit=300):
    handler, seen = target(responses)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    budget = Budget(requests_limit, 20, 300)
    findings = []

    def add_finding(f: RawFinding):
        f.validate()
        fid = f"F-{len(findings) + 1:04d}"
        findings.append((fid, f))
        return fid, "A-002"

    def audit(*a, **k):
        pass

    ctx = SimpleNamespace(budget=budget, add_finding=add_finding, audit=audit)
    scope = Scope.from_summary(SUMMARY)
    probe = AttackProbe(ctx, client, scheme="https", host_min_interval=0)  # 테스트는 속도 제한 끔
    return probe, scope, budget, seen, findings, client


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ probe_http

def test_probe_http_finds_endpoints_from_js_and_openapi():
    responses = {
        "www.jobnest.test/": (200, {"content-type": "text/html", "server": "nginx"},
                              "<html><script>" + WWW_APP_JS.decode() + "</script></html>"),
        "api.jobnest.test/": (200, {"content-type": "application/json", "x-powered-by": "PHP/8.1.2"}, {"status": "ok"}),
        "api.jobnest.test/openapi.json": (200, {"content-type": "application/json"}, API_OPENAPI),
    }
    probe, scope, budget, seen, _, client = make(responses)
    out = run(probe._probe_http(_args(scope, "A-001"), scope))
    client_close(client)

    assert out.data["status"] == "ok" and out.data["http_status"] == 200
    assert out.data["headers"]["server"] == "nginx"
    paths = {e["path"] for e in out.data["endpoints"]}
    assert "/api/v1/jobs" in paths and "/api/v1/applicants" in paths
    # 모든 요청에 식별 User-Agent, 메서드는 GET만
    assert all(r.headers["user-agent"] == USER_AGENT for r in seen)
    assert {r.method for r in seen} == {"GET"}
    # 응답 원문(개인정보)·host는 LLM 데이터에 없다
    assert "jobnest.test" not in json.dumps(out.data, ensure_ascii=False)


def test_probe_http_registers_openapi_endpoints_with_scope_rules():
    responses = {
        "api.jobnest.test/": (200, {"content-type": "application/json"}, {"status": "ok"}),
        "api.jobnest.test/openapi.json": (200, {"content-type": "application/json"}, API_OPENAPI),
    }
    probe, scope, budget, seen, _, client = make(responses)
    out = run(probe._probe_http(_args(scope, "A-002"), scope))
    client_close(client)

    by_path = {e["path"]: e for e in out.data["endpoints"]}
    assert by_path["/api/v1/applicants"]["callable"] is True          # GET
    assert by_path["/api/v1/applicants/{applicant_id}"]["callable"] is False  # 번호 변수
    assert "/api/v1/applicants" in scope.endpoints_of("A-002")[0]["path"] or scope.endpoints  # Scope에 등록됨
    # post는 등록되지 않는다(GET만 뽑음)
    assert all(e["method"] == "GET" for e in out.data["endpoints"])


def test_probe_http_unreachable_returns_status_not_crash():
    def boom(request):
        raise httpx.ConnectError("no route")

    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    budget = Budget(300, 20, 300)
    ctx = SimpleNamespace(budget=budget, add_finding=lambda f: ("F", "A"), audit=lambda *a, **k: None)
    scope = Scope.from_summary(SUMMARY)
    probe = AttackProbe(ctx, client, host_min_interval=0)
    out = run(probe._probe_http(_args(scope, "A-001"), scope))
    client_close(client)
    assert out.data["status"] == "unreachable"


# ------------------------------------------------------------------ check_unauth_api (#16)

def test_unauth_api_records_pii_finding():
    responses = {
        "api.jobnest.test/": (200, {"content-type": "application/json"}, {"status": "ok"}),
        "api.jobnest.test/openapi.json": (200, {"content-type": "application/json"}, API_OPENAPI),
        "api.jobnest.test/api/v1/applicants": (200, {"content-type": "application/json"}, APPLICANTS),
    }
    probe, scope, budget, seen, findings, client = make(responses)
    run(probe._probe_http(_args(scope, "A-002"), scope))
    eid = next(e["endpoint_id"] for e in scope.endpoints_of("A-002") if e["path"] == "/api/v1/applicants")
    out = run(probe._check_unauth_api(_eargs(scope, "A-002", eid), scope))
    client_close(client)

    assert out.data["status"] == "finding" and out.data["check_id"] == 16
    assert out.data["finding_id"] == findings[0][0]
    # 가린 증거만 나가고 실제 이메일·전화번호는 없다
    ev = out.data["evidence"]
    assert "가림" in ev and "2건" in ev  # 실제로 돌아온 항목 수(total이 아니라 반환된 개수)
    assert "example.com" not in ev and "010-0000" not in ev
    assert len(ev) <= 200
    # 저장된 발견: #16, situation pii, location은 저장만(증거에 원문 없음)
    fid, f = findings[0]
    assert f.check_id == 16 and f.situation == "pii"
    assert f.host == "api.jobnest.test" and f.location.startswith("GET https://")
    assert "example.com" not in f.evidence


@pytest.mark.parametrize("status, ctype, body, expect", [
    (401, "application/json", {"detail": "인증이 필요합니다"}, "clean"),
    (403, "text/html", "forbidden", "clean"),
    (200, "application/json", {"page": 1, "total": 2, "items": [{"id": 1, "title": "백엔드"}]}, "clean"),
    (200, "application/json", APPLICANTS, "finding"),
])
def test_unauth_api_status_matrix(status, ctype, body, expect):
    responses = {
        "api.jobnest.test/": (200, {"content-type": "application/json"}, {"status": "ok"}),
        "api.jobnest.test/openapi.json": (200, {"content-type": "application/json"}, API_OPENAPI),
        "api.jobnest.test/api/v1/applicants": (status, {"content-type": ctype}, body),
    }
    probe, scope, budget, seen, findings, client = make(responses)
    run(probe._probe_http(_args(scope, "A-002"), scope))
    eid = next(e["endpoint_id"] for e in scope.endpoints_of("A-002") if e["path"] == "/api/v1/applicants")
    out = run(probe._check_unauth_api(_eargs(scope, "A-002", eid), scope))
    client_close(client)
    assert out.data["status"] == expect
    assert len(findings) == (1 if expect == "finding" else 0)


# ------------------------------------------------------------------ 예산·속도·중지

def test_request_budget_stops_extra_requests():
    responses = {"www.jobnest.test/": (200, {"content-type": "text/html"}, "<html></html>")}
    probe, scope, budget, seen, _, client = make(responses, requests_limit=1)
    out = run(probe._probe_http(_args(scope, "A-001"), scope))
    client_close(client)
    # 루트 1건으로 예산 소진 → openapi.json 요청은 보내지 않는다
    assert budget.requests_used == 1 and len(seen) == 1


def test_scan_stop_propagates_before_request():
    responses = {"www.jobnest.test/": (200, {}, "x")}
    probe, scope, budget, seen, _, client = make(responses)
    budget.stop_requested = True
    with pytest.raises(ScanStopped):
        run(probe._probe_http(_args(scope, "A-001"), scope))
    client_close(client)
    assert seen == []


def test_throttle_spaces_requests_per_host():
    responses = {
        "api.jobnest.test/": (200, {"content-type": "application/json"}, {"ok": 1}),
        "api.jobnest.test/openapi.json": (200, {"content-type": "application/json"}, {"paths": {}}),
    }
    handler, seen = target(responses)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    budget = Budget(300, 20, 300)
    ctx = SimpleNamespace(budget=budget, add_finding=lambda f: ("F", "A"), audit=lambda *a, **k: None)
    scope = Scope.from_summary(SUMMARY)
    probe = AttackProbe(ctx, client, host_min_interval=0.05)  # 두 요청 사이 최소 간격

    import time
    t0 = time.monotonic()
    run(probe._probe_http(_args(scope, "A-002"), scope))
    elapsed = time.monotonic() - t0
    client_close(client)
    assert len(seen) == 2 and elapsed >= 0.05  # 호스트당 속도 제한이 걸렸다


# ------------------------------------------------------------------ 가드와 함께

def test_handlers_plug_into_guard():
    responses = {
        "api.jobnest.test/": (200, {"content-type": "application/json"}, {"status": "ok"}),
        "api.jobnest.test/openapi.json": (200, {"content-type": "application/json"}, API_OPENAPI),
        "api.jobnest.test/api/v1/applicants": (200, {"content-type": "application/json"}, APPLICANTS),
    }
    handler, seen = target(responses)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    budget = Budget(300, 20, 300)
    rows = []

    def add_finding(f):
        f.validate()
        return "F-0001", "A-002"

    def audit(actor, tool, args, result_summary=None, rejected=False, reject_reason=None):
        rows.append((tool, rejected, reject_reason))

    ctx = SimpleNamespace(budget=budget, add_finding=add_finding, audit=audit)
    scope = Scope.from_summary(SUMMARY)
    hs = build_attack_handlers(ctx, client, host_min_interval=0)
    guard = Guard("attack", scope, budget, audit, hs)

    run(guard.call("probe_http", {"asset_id": "A-002"}))
    eid = next(e["endpoint_id"] for e in scope.endpoints_of("A-002") if e["path"] == "/api/v1/applicants")
    out = run(guard.call("check_unauth_api", {"asset_id": "A-002", "endpoint_id": eid}))
    # 번호 변수 엔드포인트는 가드가 막는다(핸들러에 닿지 않음)
    tid = next(e["endpoint_id"] for e in scope.endpoints_of("A-002")
               if e["path"] == "/api/v1/applicants/{applicant_id}")
    blocked = run(guard.call("check_unauth_api", {"asset_id": "A-002", "endpoint_id": tid}))
    client_close(client)

    assert out["status"] == "finding" and out["finding_id"] == "F-0001"
    assert "번호 변수" in blocked["reason"]
    assert ("check_unauth_api", True, blocked["reason"]) in [(t, r, rr) for t, r, rr in rows]


# ------------------------------------------------------------------ 보조

def _args(scope, asset_id):
    from a2d.agents.tools import AssetArgs
    return AssetArgs(asset_id=asset_id)


def _eargs(scope, asset_id, endpoint_id):
    from a2d.agents.tools import EndpointArgs
    return EndpointArgs(asset_id=asset_id, endpoint_id=endpoint_id)


def client_close(client):
    run(client.aclose())
