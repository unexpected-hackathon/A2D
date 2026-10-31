"""조치 가이드(FR-07·08)와 질의응답(FR-12)이 LLM에 붙는지 가짜 vLLM 서버로 확인한다. 실제 네트워크는 쓰지 않는다."""

import asyncio
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from types import SimpleNamespace

from a2d import agents
from a2d.agents.tools import Scope, ToolResult
from a2d.catalog import GUIDES
from a2d.config import Settings
from a2d.engine.base import Budget, ScanStopped
from a2d.main import create_app

from .test_api import EMAIL, ORIGIN, PASSWORD, login, setup_domain, wait_done


class FakeVllm:
    """/v1/chat/completions만 흉내 낸다. reply(body, n)이 답 문자열을 만든다(n = 몇 번째 요청인지)."""

    def __init__(self, reply, status: int = 200, reject_schema: bool = False):
        self.reply = reply
        self.status = status
        self.reject_schema = reject_schema
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen3-8b"}]})
        body = json.loads(request.content)
        self.requests.append(body)
        if self.reject_schema and "response_format" in body:
            return httpx.Response(400, json={"error": "response_format not supported"})
        if self.status != 200:
            return httpx.Response(self.status, text="boom")
        reply = self.reply(body, len(self.requests))
        # 도구 호출 답은 reply가 message dict를 그대로 돌려준다(content는 null). 글자면 content로 감싼다.
        message = reply if isinstance(reply, dict) else {"role": "assistant", "content": reply}
        return httpx.Response(200, json={"choices": [{"message": message}]})


def data_of(body: dict) -> dict:
    text = body["messages"][1]["content"]
    return json.loads(re.search(r"<data>\n(.*)\n</data>", text, re.S).group(1))


def good_item(body: dict) -> str:
    d = data_of(body)
    f = d["finding"]
    return json.dumps({
        "finding_id": f["finding_id"],
        "title": f"{f['asset_alias']}에서 고칠 문제",
        "why_risky": f"{f['asset_alias']} 서버의 {f['check_name']} 문제로 누구나 정보를 볼 수 있습니다.",
        "expected_damage": "회원 정보가 새어 나갈 수 있습니다.",
        "fix_step_ids": [1],
    }, ensure_ascii=False)


def llm_settings(tmp_path) -> Settings:
    return Settings(
        admin_email=EMAIL, admin_password=PASSWORD, db_path=str(tmp_path / "a2d.sqlite3"),
        web_origins=[ORIGIN], verify_mode="trust", fixture_step_sec=0,
        llm_base_url="http://llm.test/v1", llm_api_key="test-key",
    )


@pytest.fixture
def make_client(tmp_path):
    """가짜 vLLM을 끼운 API 클라이언트를 만든다."""
    clients = []

    def make(fake: FakeVllm) -> TestClient:
        settings = llm_settings(tmp_path)
        c = TestClient(create_app(settings), base_url="http://testserver", headers={"Origin": ORIGIN})
        c.__enter__()
        clients.append(c)
        llm = agents.LlmClient(settings, transport=httpx.MockTransport(fake))
        c.app.state.llm = llm
        c.app.state.svc.llm = llm
        login(c)
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def run_scan(c: TestClient) -> str:
    domain_id = setup_domain(c)
    scan_id = c.post(f"/api/v1/domains/{domain_id}/scans").json()["scan_id"]
    assert wait_done(c, scan_id)["status"] == "done"
    return scan_id


def template_titles():
    return {GUIDES[16].title, GUIDES[8].title, GUIDES[18].title}


# ------------------------------------------------------------------ 조치 가이드


def test_report_from_llm(make_client):
    fake = FakeVllm(lambda body, n: good_item(body))
    c = make_client(fake)
    scan_id = run_scan(c)
    report = c.get(f"/api/v1/scans/{scan_id}/report").json()
    assert report["source"] == "llm" and report["verification"] == {"passed": 3, "total": 3}
    assert [i["title"] for i in report["items"]] == ["api에서 고칠 문제", "www에서 고칠 문제", "admin에서 고칠 문제"]
    assert [i["fix_steps"] for i in report["items"]] == [[GUIDES[16].fix_steps[0]], [GUIDES[8].fix_steps[0]],
                                                         [GUIDES[18].fix_steps[0]]]
    assert [(i["rank"], i["fix_minutes"], i["safety_score_after"]) for i in report["items"]] == [
        (1, 60, 30), (2, 10, 49), (3, 30, 100)]
    assert all(i["verified"] for i in report["items"])

    # 요청 형식과 보내지 않는 것(위치 URL)
    assert len(fake.requests) == 3
    body = fake.requests[0]
    assert body["model"] == "qwen3-8b" and body["response_format"]["type"] == "json_schema"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    sent = json.dumps(fake.requests, ensure_ascii=False)
    assert "https://" not in sent and "location" not in sent

    # 다시 불러도 LLM을 다시 부르지 않는다
    c.get(f"/api/v1/scans/{scan_id}/report")
    assert len(fake.requests) == 3


def test_report_retries_with_reason_then_passes(make_client):
    def reply(body, n):
        if len(body["messages"]) == 2:  # 첫 요청은 없는 CVE를 지어낸다
            out = json.loads(good_item(body))
            out["why_risky"] += " CVE-2024-12345 약점입니다."
            return json.dumps(out, ensure_ascii=False)
        return good_item(body)

    fake = FakeVllm(reply)
    c = make_client(fake)
    report = c.get(f"/api/v1/scans/{run_scan(c)}/report").json()
    assert report["source"] == "llm" and report["verification"] == {"passed": 3, "total": 3}
    retries = [b for b in fake.requests if len(b["messages"]) == 4]
    assert len(retries) == 3 and "증거에 없는 CVE" in retries[0]["messages"][3]["content"]


def test_report_item_falls_back_after_two_failures(make_client):
    def reply(body, n):
        out = json.loads(good_item(body))
        if data_of(body)["finding"]["check_id"] == 16:
            out["fix_step_ids"] = [9]  # 문안에 없는 조치
        return json.dumps(out, ensure_ascii=False)

    c = make_client(FakeVllm(reply))
    report = c.get(f"/api/v1/scans/{run_scan(c)}/report").json()
    assert report["source"] == "llm" and report["verification"] == {"passed": 2, "total": 3}
    first = report["items"][0]
    assert first["title"] == GUIDES[16].title and first["fix_steps"] == list(GUIDES[16].fix_steps)
    assert report["items"][1]["title"] == "www에서 고칠 문제"


@pytest.mark.parametrize("fake", [
    FakeVllm(lambda body, n: "죄송합니다. 답할 수 없습니다."),
    FakeVllm(lambda body, n: "", status=500),
])
def test_report_template_when_llm_unusable(make_client, fake):
    c = make_client(fake)
    report = c.get(f"/api/v1/scans/{run_scan(c)}/report").json()
    assert report["source"] == "template" and report["verification"] == {"passed": 3, "total": 3}
    assert {i["title"] for i in report["items"]} == template_titles()


def test_schema_rejected_falls_back_to_plain_json(make_client):
    fake = FakeVllm(lambda body, n: "```json\n" + good_item(body) + "\n```", reject_schema=True)
    c = make_client(fake)
    report = c.get(f"/api/v1/scans/{run_scan(c)}/report").json()
    assert report["source"] == "llm" and report["verification"]["passed"] == 3
    assert "response_format" not in fake.requests[-1]


# ------------------------------------------------------------------ 근거 검증 규칙


def _item_case():
    template = {"rank": 1, "finding_ids": ["F-0001"], "title": GUIDES[16].title,
                "why_risky": GUIDES[16].why_risky.format(asset="api"), "expected_damage": GUIDES[16].expected_damage,
                "fix_steps": list(GUIDES[16].fix_steps), "fix_minutes": 60, "safety_score_after": 30, "verified": True}
    detail = {"finding_id": "F-0001", "check_id": 16, "asset_alias": "api", "situation": "개인정보 형태 데이터 반환",
              "score": {"risk_score": 100}, "evidence": "200 응답, 지원자 20명 목록", "cves": []}
    row = {"finding_id": "F-0001", "fix_minutes": 60, "safety_score_after": 30, "asset_alias": "api"}
    out = {"finding_id": "F-0001", "title": "회원 정보가 로그인 없이 보입니다",
           "why_risky": "api 서버에서 지원자 20명의 연락처가 그대로 보입니다.",
           "expected_damage": "전체 회원 정보가 유출될 수 있습니다.", "fix_step_ids": [3, 1]}
    return out, template, detail, row


def test_verify_accepts_grounded_item():
    out, template, detail, row = _item_case()
    item, errors = agents.verify_report_item(out, template, detail, row, {"api", "www", "admin"})
    assert errors == []
    assert item["fix_steps"] == [GUIDES[16].fix_steps[0], GUIDES[16].fix_steps[2]]  # 문안 순서
    assert item["finding_ids"] == ["F-0001"] and item["fix_minutes"] == 60


@pytest.mark.parametrize("patch, reason", [
    ({"finding_id": "F-9999"}, "finding_id"),
    ({"why_risky": "api 서버에서 지원자 5000명의 연락처가 보입니다."}, "데이터에 없는 숫자"),
    ({"why_risky": "api와 www 서버 모두에서 연락처가 보입니다."}, "다른 항목의 자산"),
    ({"why_risky": "api 서버에 CVE-2021-44228 약점이 있습니다."}, "증거에 없는 CVE"),
    ({"fix_step_ids": [0]}, "없는 조치 번호"),
    ({"fix_step_ids": []}, "fix_step_ids가 비어"),
    ({"expected_damage": "会员信息可能泄露。"}, "한자"),
    ({"title": "가" * 41}, "40자"),
    ({"title": ""}, "title가 비어"),
])
def test_verify_rejects(patch, reason):
    out, template, detail, row = _item_case()
    item, errors = agents.verify_report_item({**out, **patch}, template, detail, row, {"api", "www", "admin"})
    assert item is None and any(reason in e for e in errors), errors


def test_parse_json_tolerates_wrapping():
    assert agents.parse_json('<think>음</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    assert agents.parse_json("설명입니다") is None
    assert agents.parse_json("[1, 2]") is None


# ------------------------------------------------------------------ 질의응답


def qa_reply(answer: str, ids_from_findings=True, extra_ids=()):
    def reply(body, n):
        if "<findings>" not in body["messages"][1]["content"]:
            return good_item(body)
        text = body["messages"][1]["content"]
        findings = json.loads(re.search(r"<findings>\n(.*)\n</findings>", text, re.S).group(1))
        ids = [f["finding_id"] for f in findings if f["check_id"] == 8] if ids_from_findings else []
        return json.dumps({"answer": answer, "finding_ids": ids + list(extra_ids)}, ensure_ascii=False)
    return reply


def test_question_answered_with_grounds(make_client):
    fake = FakeVllm(qa_reply("www의 backup.zip은 주소만 알면 누구나 내려받을 수 있습니다.", extra_ids=["F-9999"]))
    c = make_client(fake)
    scan_id = run_scan(c)
    f8 = next(f["finding_id"] for f in c.get(f"/api/v1/scans/{scan_id}/findings").json()["items"] if f["check_id"] == 8)
    r = c.post(f"/api/v1/scans/{scan_id}/questions", json={"question": "백업 파일은 왜 위험해요?"})
    assert r.status_code == 200, r.text
    assert r.json() == {"answer": "www의 backup.zip은 주소만 알면 누구나 내려받을 수 있습니다.",
                        "finding_ids": [f8], "verification": {"passed": True}}
    qa = fake.requests[-1]
    assert "백업 파일은 왜 위험해요?" in qa["messages"][1]["content"] and "https://" not in qa["messages"][1]["content"]


@pytest.mark.parametrize("reply, passed", [
    (qa_reply("점검과 무관한 질문입니다.", ids_from_findings=False), True),
    (qa_reply("근거 없는 답", ids_from_findings=False, extra_ids=["F-9999"]), True),
    (qa_reply("CVE-2021-44228 때문에 위험합니다."), False),
    (qa_reply("备份文件很危险。"), False),
])
def test_question_without_grounds(make_client, reply, passed):
    c = make_client(FakeVllm(reply))
    scan_id = run_scan(c)
    r = c.post(f"/api/v1/scans/{scan_id}/questions", json={"question": "아무 질문"})
    assert r.status_code == 200
    assert r.json() == {"answer": agents.NO_GROUND, "finding_ids": [], "verification": {"passed": passed}}


def test_question_503_when_llm_fails(make_client):
    c = make_client(FakeVllm(lambda body, n: good_item(body)))
    scan_id = run_scan(c)
    c.app.state.svc.llm._transport = httpx.MockTransport(FakeVllm(lambda b, n: "", status=503))
    r = c.post(f"/api/v1/scans/{scan_id}/questions", json={"question": "백업 파일은 왜 위험해요?"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "LLM_UNAVAILABLE"


def test_chat_raises_on_connection_error():
    def boom(request):
        raise httpx.ConnectError("no route")

    llm = agents.LlmClient(Settings(llm_base_url="http://llm.test/v1"), transport=httpx.MockTransport(boom))
    with pytest.raises(agents.LlmError):
        asyncio.run(llm.chat([{"role": "user", "content": "hi"}], max_tokens=10, timeout=1))


def test_other_400_keeps_schema():
    """문맥 길이 초과 같은 400은 schema를 끄지 않는다."""
    fake = FakeVllm(lambda b, n: "", status=400)
    llm = agents.LlmClient(Settings(llm_base_url="http://llm.test/v1"), transport=httpx.MockTransport(fake))
    with pytest.raises(agents.LlmError):
        asyncio.run(llm.chat([{"role": "user", "content": "hi"}], max_tokens=10, timeout=1, schema={"type": "object"}))
    assert llm._schema_ok is True and len(fake.requests) == 2


def test_question_prompt_is_capped():
    fake = FakeVllm(lambda b, n: json.dumps({"answer": "답", "finding_ids": []}))
    llm = agents.LlmClient(Settings(llm_base_url="http://llm.test/v1"), transport=httpx.MockTransport(fake))
    findings = [{"finding_id": f"F-{i:04d}", "check_id": 8, "check_name": "백업", "asset_alias": "www",
                 "situation": "파일 형식까지 확인", "score": {"risk_score": 100 - i}, "evidence": "가" * 200, "cves": []}
                for i in range(15)]
    asyncio.run(agents.answer_question(llm, "질문", findings))
    text = fake.requests[0]["messages"][1]["content"]
    sent = json.loads(re.search(r"<findings>\n(.*)\n</findings>", text, re.S).group(1))
    assert 1 <= len(sent) < 15 and len(json.dumps(sent, ensure_ascii=False, separators=(",", ":"))) <= agents.QA_MAX_CHARS
    assert sent[0]["finding_id"] == "F-0000"  # 위험 점수가 높은 것이 남는다


# ------------------------------------------------------------------ 추가 점검 (Attack, FR-04)

ATTACK_SUMMARY = {
    "assets": [
        {"asset_id": "A-001", "host": "www.example.test", "alias": "www", "tags": ["web"], "importance": 4},
        {"asset_id": "A-002", "host": "api.example.test", "alias": "api", "tags": ["api"], "importance": 5},
    ],
    "findings": [{"asset_id": "A-002", "check_id": 16, "situation": "개인정보 형태 데이터 반환"}],
}


def tool_call_reply(*steps):
    """가짜 vLLM이 요청 n번째마다 도구 호출 하나를 돌려준다. steps = (도구 이름, 인자 dict) 차례.

    steps를 다 쓰면 도구 없는 답(content)을 돌려줘 루프가 스스로 멈추게 한다.
    """
    def reply(body, n):
        if n <= len(steps):
            name, args = steps[n - 1]
            return {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call_{n}", "type": "function",
                 "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}
        return "더 볼 곳이 없습니다."
    return reply


def attack_setup(reply, *, budget=None, requests_limit=300, tool_calls_limit=20):
    """run_attack을 직접 돌리는 준비: 가짜 LLM, 가짜 핸들러, 감사 기록을 모은 ctx를 만든다."""
    settings = Settings(llm_base_url="http://llm.test/v1", llm_api_key="k")
    fake = FakeVllm(reply)
    llm = agents.LlmClient(settings, transport=httpx.MockTransport(fake))
    budget = budget or Budget(requests_limit, tool_calls_limit, 300)
    rows: list[dict] = []
    calls: list[tuple[str, dict]] = []

    def audit(actor, tool, args, result_summary=None, rejected=False, reject_reason=None):
        rows.append({"actor": actor, "tool": tool, "args": args, "result_summary": result_summary,
                     "rejected": rejected, "reject_reason": reject_reason})

    async def probe(args, scope):
        calls.append(("probe_http", args.model_dump()))
        budget.requests_used += 1
        e = scope.add_endpoint("A-002", "GET", "/api/v1/jobs")
        return ToolResult({"status": "ok", "endpoints": [e.endpoint_id]}, "엔드포인트 1개")

    async def unauth(args, scope):
        calls.append(("check_unauth_api", args.model_dump()))
        budget.requests_used += 1
        return ToolResult({"status": "finding", "finding_id": "F-0012", "evidence": "200 응답(가림)"}, "발견 1건")

    ctx = SimpleNamespace(budget=budget, audit=audit)
    handlers = {"probe_http": probe, "check_unauth_api": unauth}
    return llm, ctx, fake, rows, calls, handlers


def test_attack_runs_tools_until_finish():
    reply = tool_call_reply(
        ("list_assets", {}),
        ("probe_http", {"asset_id": "A-002"}),
        ("check_unauth_api", {"asset_id": "A-002", "endpoint_id": "E-01"}),
        ("finish_scan", {"reason": "더 볼 곳 없음"}),
    )
    llm, ctx, fake, rows, calls, handlers = attack_setup(reply)
    asyncio.run(agents.run_attack(llm, ctx, ATTACK_SUMMARY, handlers=handlers))

    assert calls == [("probe_http", {"asset_id": "A-002"}),
                     ("check_unauth_api", {"asset_id": "A-002", "endpoint_id": "E-01"})]
    assert [r["tool"] for r in rows] == ["list_assets", "probe_http", "check_unauth_api", "finish_scan"]
    assert all(not r["rejected"] for r in rows)
    assert rows[-1]["result_summary"] == "추가 점검 종료: 더 볼 곳 없음"
    assert ctx.budget.tool_calls_used == 4

    # finish_scan 뒤에는 LLM을 다시 부르지 않는다. 도구·요청은 보내되 위치 URL은 보내지 않는다.
    assert len(fake.requests) == 4
    body = fake.requests[0]
    assert body["tool_choice"] == "auto" and "response_format" not in body
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    names = [t["function"]["name"] for t in body["tools"]]
    assert names == ["list_assets", "probe_http", "check_unauth_api", "finish_scan"]
    assert "example.test" not in json.dumps(fake.requests, ensure_ascii=False)
    # 시스템 프롬프트의 예산 숫자는 실제 Budget에서 온다(하드코딩 아님)
    system = body["messages"][0]["content"]
    assert "도구 20회" in system and "요청 300건" in system


def test_attack_guard_rejection_is_audited():
    reply = tool_call_reply(
        ("check_unauth_api", {"asset_id": "A-002", "endpoint_id": "E-99"}),  # 찾은 적 없는 엔드포인트
        ("probe_http", {"asset_id": "A-404"}),  # 소유권 밖 자산
        ("finish_scan", {"reason": "끝"}),
    )
    llm, ctx, fake, rows, calls, handlers = attack_setup(reply)
    asyncio.run(agents.run_attack(llm, ctx, ATTACK_SUMMARY, handlers=handlers))

    assert calls == []  # 거부된 호출은 핸들러에 닿지 않는다
    rejected = [r for r in rows if r["rejected"]]
    assert [r["tool"] for r in rejected] == ["check_unauth_api", "probe_http"]
    assert "찾은 적 없는 엔드포인트" in rejected[0]["reject_reason"]
    assert "소유권이 확인된 자산이 아님" in rejected[1]["reject_reason"]
    assert rows[-1]["tool"] == "finish_scan" and rows[-1]["rejected"] is False


def test_attack_stops_when_tool_budget_exhausted():
    # 도구 2회 예산. finish_scan을 부르기 전에 예산이 끝나면 멈춘다.
    reply = tool_call_reply(
        ("probe_http", {"asset_id": "A-002"}),
        ("probe_http", {"asset_id": "A-001"}),
        ("check_unauth_api", {"asset_id": "A-002", "endpoint_id": "E-01"}),
    )
    llm, ctx, fake, rows, calls, handlers = attack_setup(reply, tool_calls_limit=2)
    asyncio.run(agents.run_attack(llm, ctx, ATTACK_SUMMARY, handlers=handlers))
    assert ctx.budget.tool_calls_used == 2
    assert len(rows) == 2 and all(not r["rejected"] for r in rows)
    assert len(fake.requests) == 2  # 예산 소진 후 LLM을 다시 부르지 않는다


def test_attack_stops_on_llm_error():
    fake = FakeVllm(lambda body, n: "", status=500)
    settings = Settings(llm_base_url="http://llm.test/v1")
    llm = agents.LlmClient(settings, transport=httpx.MockTransport(fake))
    rows: list[dict] = []

    async def probe(args, scope):  # 등록만 해 둔다. LLM 요청이 먼저 실패해 불리지 않는다
        rows.append(("probe", None))
        return ToolResult({"status": "ok"}, "ok")

    ctx = SimpleNamespace(budget=Budget(300, 20, 300),
                          audit=lambda *a, **k: rows.append((a, k)))
    asyncio.run(agents.run_attack(llm, ctx, ATTACK_SUMMARY, handlers={"probe_http": probe}))
    assert rows == []  # 첫 요청이 실패하면 도구를 한 번도 부르지 않는다


def test_attack_scan_stop_propagates():
    reply = tool_call_reply(("list_assets", {}), ("finish_scan", {"reason": "끝"}))
    llm, ctx, fake, rows, calls, handlers = attack_setup(reply)
    ctx.budget.stop_requested = True
    with pytest.raises(ScanStopped):
        asyncio.run(agents.run_attack(llm, ctx, ATTACK_SUMMARY, handlers=handlers))


def test_attack_noop_without_llm():
    llm = agents.LlmClient(Settings())  # 주소 없음 → configured False
    rows: list[dict] = []
    ctx = SimpleNamespace(budget=Budget(300, 20, 300),
                          audit=lambda *a, **k: rows.append((a, k)))
    asyncio.run(agents.run_attack(llm, ctx, ATTACK_SUMMARY))
    assert rows == []
