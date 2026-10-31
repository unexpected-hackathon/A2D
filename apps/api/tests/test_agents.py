"""조치 가이드(FR-07·08)와 질의응답(FR-12)이 LLM에 붙는지 가짜 vLLM 서버로 확인한다. 실제 네트워크는 쓰지 않는다."""

import asyncio
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from a2d import agents
from a2d.catalog import GUIDES
from a2d.config import Settings
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
        content = self.reply(body, len(self.requests))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


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
