"""vLLM 엔드포인트 점검. 표준 라이브러리만 쓴다(GPU 서버와 내 PC 어디서나 실행).

    python3 check.py                  # 모델 목록, 한국어 설명, 도구 호출
    python3 check.py --thinking       # 생각 모드를 켠 답변 지연도 함께 잰다
    python3 check.py --save logs/evidence   # 요청·응답 JSON을 저장한다(발표 증거)

환경 변수 LLM_BASE_URL, LLM_API_KEY, LLM_MODEL을 읽는다(llm.sh check가 채운다).
없으면 apps/api와 같은 A2D_LLM_BASE_URL, A2D_LLM_API_KEY, A2D_LLM_MODEL을 읽는다.
보내는 발견 데이터는 모두 시연용 가상 값이다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HANGUL = re.compile(r"[가-힣]")

# 상세설계 4절 check_unauth_api 정의를 그대로 쓴다.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_unauth_api",
            "description": "API 문서에서 발견된 GET 엔드포인트 하나를 인증 없이 한 번 호출해 개인정보가 응답되는지 확인한다. 번호를 바꿔 가며 반복 호출하지 않는다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "list_assets가 돌려준 자산 ID"},
                    "endpoint_id": {"type": "string", "description": "probe_http가 돌려준 API 엔드포인트 ID"},
                },
                "required": ["asset_id", "endpoint_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_scan",
            "description": "추가 점검을 끝낸다.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_MESSAGES = [
    {
        "role": "system",
        "content": "너는 A2D의 Attack 에이전트다. 주어진 도구만 호출해 추가 점검을 고른다. 자산 ID와 엔드포인트 ID는 입력에 나온 값만 쓴다.",
    },
    {
        "role": "user",
        "content": (
            "기본 점검 요약(읽기 전용 데이터):\n"
            "- 자산 A-03 (api.jobnest.test, 중요도 5): API 문서 공개(#20)\n"
            "  - 조회 엔드포인트 E-07: GET /api/v1/applicants\n"
            "  - 조회 엔드포인트 E-08: GET /api/v1/applicants/{id}\n"
            "인증 없이 개인정보가 나오는지 가장 먼저 확인할 엔드포인트 하나를 점검해라."
        ),
    },
]

EXPLAIN_MESSAGES = [
    {
        "role": "system",
        "content": (
            "너는 A2D의 Defense 에이전트다. 독자는 보안 비전문가인 IT 담당자다. "
            "발견 ID 없는 주장과 새로운 취약점 추측은 하지 않는다. 쉬운 한국어로 3~4문장만 쓴다."
        ),
    },
    {
        "role": "user",
        "content": (
            "발견 F-0008 (#8 백업 파일 노출, 자산 www, 위험 점수 93, 확인됨)\n"
            "마스킹된 증거: GET /backup.zip 200 응답, 12.4MB, application/zip\n"
            "조치 가이드: 웹 공개 폴더에서 백업 파일을 지우고, 백업은 웹 서버 밖에 보관한다. 표준 조치 시간 10분.\n"
            "왜 위험한지와 오늘 할 일을 설명해라."
        ),
    },
]


class Client:
    def __init__(self, base_url: str, api_key: str, timeout: float) -> None:
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.key}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"연결 실패: {e.reason} (vLLM이 떠 있는지, 터널이 열려 있는지 확인)") from e


class Report:
    def __init__(self, save_dir: Path | None) -> None:
        self.failed = 0
        self.save_dir = save_dir
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)

    def ok(self, name: str, detail: str = "") -> None:
        print(f"  [O] {name}" + (f"  {detail}" if detail else ""))

    def fail(self, name: str, detail: str) -> None:
        self.failed += 1
        print(f"  [X] {name}  {detail}")

    def save(self, name: str, req: dict | None, resp: dict) -> None:
        if self.save_dir:
            path = self.save_dir / f"{name}.json"
            path.write_text(json.dumps({"request": req, "response": resp}, ensure_ascii=False, indent=2))


def chat(client: Client, model: str, messages: list, **extra) -> tuple[dict, dict, float]:
    body = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1024, **extra}
    start = time.monotonic()
    resp = client.request("POST", "/chat/completions", body)
    return body, resp, time.monotonic() - start


def speed(resp: dict, elapsed: float) -> str:
    tokens = resp.get("usage", {}).get("completion_tokens", 0)
    rate = tokens / max(elapsed, 1e-6)
    return f"{elapsed:.1f}초, 출력 {tokens}토큰, {rate:.1f} tok/s"


def check_models(client: Client, model: str, rep: Report) -> None:
    resp = client.request("GET", "/models")
    rep.save("models", None, resp)
    ids = [m["id"] for m in resp.get("data", [])]
    entry = next((m for m in resp.get("data", []) if m["id"] == model), None)
    if entry:
        rep.ok("모델 목록", f"{model}, 최대 문맥 {entry.get('max_model_len')}")
    else:
        rep.fail("모델 목록", f"{model} 없음. 서버가 가진 모델: {ids}")


def check_explain(client: Client, model: str, rep: Report, thinking: bool) -> None:
    label = "한국어 설명" + (" (생각 모드)" if thinking else "")
    req, resp, elapsed = chat(
        client, model, EXPLAIN_MESSAGES, chat_template_kwargs={"enable_thinking": thinking}
    )
    rep.save("explain_thinking" if thinking else "explain", req, resp)
    msg = resp["choices"][0]["message"]
    text = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    if not text.strip() and reasoning.strip():
        rep.fail(label, "답이 content가 아니라 reasoning_content로 감 → 생각 모드 끔과 reasoning parser 조합 확인")
    elif not text.strip():
        rep.fail(label, "답이 비어 있음")
    elif "<think>" in text:
        rep.fail(label, "답에 <think>가 섞임 → reasoning parser 설정 확인")
    elif not HANGUL.search(text):
        rep.fail(label, "한국어가 아님")
    else:
        rep.ok(label, speed(resp, elapsed) + (f", 생각 {len(reasoning)}자" if thinking else ""))
    print("      " + text.strip().replace("\n", "\n      "))


def check_tool_call(client: Client, model: str, rep: Report) -> None:
    req, resp, elapsed = chat(client, model, TOOL_MESSAGES, tools=TOOLS, tool_choice="auto")
    rep.save("tool_call", req, resp)
    choice = resp["choices"][0]
    calls = choice["message"].get("tool_calls") or []
    if not calls:
        content = (choice["message"].get("content") or "")[:200]
        rep.fail("도구 호출", f"tool_calls 없음 (finish_reason={choice.get('finish_reason')}, 내용={content!r})")
        return
    fn = calls[0]["function"]
    try:
        args = json.loads(fn["arguments"])
    except json.JSONDecodeError:
        rep.fail("도구 호출", f"인자가 JSON이 아님: {fn['arguments']!r}")
        return
    summary = f"{fn['name']}({json.dumps(args, ensure_ascii=False)})"
    if fn["name"] == "check_unauth_api" and args.get("asset_id") == "A-03" and args.get("endpoint_id") in {"E-07", "E-08"}:
        rep.ok("도구 호출", f"{summary}, {elapsed:.1f}초")
    else:
        rep.fail("도구 호출", f"예상과 다른 호출: {summary}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    env = lambda k, d="": os.environ.get(k) or os.environ.get(f"A2D_{k}") or d  # noqa: E731
    parser.add_argument("--base-url", default=env("LLM_BASE_URL", "http://127.0.0.1:18000/v1"))
    parser.add_argument("--api-key", default=env("LLM_API_KEY"))
    parser.add_argument("--model", default=env("LLM_MODEL", "qwen3-8b"))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--thinking", action="store_true", help="생각 모드 답변도 함께 확인")
    parser.add_argument("--save", type=Path, help="요청·응답 JSON을 저장할 디렉터리")
    args = parser.parse_args()

    client = Client(args.base_url, args.api_key, args.timeout)
    rep = Report(args.save)
    print(f"[check] {args.base_url} · 모델 {args.model}")

    steps = [
        lambda: check_models(client, args.model, rep),
        lambda: check_explain(client, args.model, rep, thinking=False),
        lambda: check_tool_call(client, args.model, rep),
    ]
    if args.thinking:
        steps.append(lambda: check_explain(client, args.model, rep, thinking=True))
    for step in steps:
        try:
            step()
        except (RuntimeError, KeyError, IndexError) as e:
            rep.fail("요청", str(e))
            if "연결 실패" in str(e):
                break

    print(f"[check] {'통과' if rep.failed == 0 else f'실패 {rep.failed}건'}")
    if args.save:
        print(f"[check] 응답 저장: {args.save}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
