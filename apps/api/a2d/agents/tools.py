"""에이전트 도구 등록표와 가드 층(상세설계 4절 "도구 호출 설계").

LLM은 도구 이름과 인자(자산 ID·엔드포인트 ID)만 제안하고, 실행 여부는 이 모듈의 Guard가 정한다.
Guard는 아래 순서로 거르고, 통과한 호출만 등록된 핸들러에 넘긴다.

1. 예산: 도구 호출 횟수(Budget.tool_calls_limit). 거부·중복 호출도 한 번으로 센다(같은 실수를 되풀이하는 루프를 막는다)
2. 허용 목록: 이 에이전트에 등록되고 핸들러가 붙은 도구만
3. 인자 검증: Pydantic 모델(extra="forbid"). 스키마에 맞지 않으면 실행하지 않는다
4. 범위: asset_id는 소유권이 확인된 자산만, endpoint_id는 그 자산에서 찾은 조회형(GET) 엔드포인트만.
   경로에 번호 변수가 있는 엔드포인트는 부르지 않는다(번호를 바꿔 가며 반복 호출하지 않는다)
5. 요청 예산: 대상에 요청을 보내는 도구는 Budget.requests_limit을 넘으면 거부
6. 중복 방지: 같은 도구를 같은 인자로 다시 부르면 저장된 결과를 돌려준다

모든 호출(거부 포함)은 ctx.audit으로 감사 기록에 남는다(FR-16, NFR-09).
점검을 실제로 하는 핸들러(probe_http, check_unauth_api 등)는 이 모듈에 없다. Guard를 만들 때 handlers로 끼운다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..engine.base import Budget, ScanStopped

log = logging.getLogger("a2d.agents.tools")


# ==================================================================== 인자 모델

class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NoArgs(ToolArgs):
    pass


class AssetArgs(ToolArgs):
    asset_id: str = Field(description="list_assets가 돌려준 자산 ID", pattern=r"^A-\d{3,}$")


class EndpointArgs(AssetArgs):
    endpoint_id: str = Field(description="probe_http가 돌려준 API 엔드포인트 ID", pattern=r"^E-\d{2,}$")


class FinishArgs(ToolArgs):
    reason: str = Field(description="추가 점검을 끝내는 이유(한 문장)", min_length=1, max_length=200)


# ==================================================================== 등록표

@dataclass(frozen=True)
class ToolSpec:
    name: str
    agent: str  # "attack" | "defense"
    description: str
    args: type[ToolArgs]
    sends_requests: bool  # 점검 대상에 요청을 보내는가(요청 예산을 본다)

    def schema(self) -> dict:
        """OpenAI 호환 tools 항목. 문맥(8,192토큰)을 아끼려고 Pydantic이 붙이는 title은 뺀다."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _strip_titles(self.args.model_json_schema()),
            },
        }


def _strip_titles(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_titles(v) for k, v in obj.items() if k != "title"}
    if isinstance(obj, list):
        return [_strip_titles(v) for v in obj]
    return obj


ATTACK_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("list_assets", "attack",
             "소유권이 확인된 자산 목록, 태그, 기본 점검 요약, 지금까지 찾은 API 엔드포인트를 본다.",
             NoArgs, sends_requests=False),
    ToolSpec("probe_http", "attack",
             "자산 하나의 웹 응답을 다시 확인하고 그 자산에서 쓰는 API 엔드포인트 ID를 찾는다.",
             AssetArgs, sends_requests=True),
    ToolSpec("check_unauth_api", "attack",
             "API 문서나 화면 코드에서 찾은 조회형(GET) 엔드포인트 하나를 인증 없이 한 번 호출해 "
             "개인정보가 응답되는지 확인한다. 번호를 바꿔 가며 반복 호출하지 않는다.",
             EndpointArgs, sends_requests=True),
    ToolSpec("finish_scan", "attack",
             "더 볼 곳이 없으면 추가 점검을 끝낸다.",
             FinishArgs, sends_requests=False),
)

TOOLS: dict[str, ToolSpec] = {t.name: t for t in ATTACK_TOOLS}

# 대상에 실제 요청을 보내는 점검 핸들러(probe_http, check_unauth_api 등)는 팀이 따로 만들어 여기에 등록한다.
# 비어 있으면 Attack 에이전트는 요청을 보내지 않는 기본 도구(list_assets·finish_scan)만 쓸 수 있다.
# (list_assets·finish_scan 핸들러는 Guard 안에 들어 있다.) run_attack이 이 표를 Guard에 끼운다.
ATTACK_HANDLERS: dict[str, "Handler"] = {}


# ==================================================================== 범위(자산·엔드포인트)

@dataclass(frozen=True)
class Asset:
    asset_id: str
    host: str  # 도구 층만 쓴다. LLM에는 보내지 않는다
    alias: str
    tags: tuple[str, ...] = ()
    importance: int = 3


@dataclass(frozen=True)
class Endpoint:
    endpoint_id: str
    asset_id: str
    method: str
    path: str
    callable: bool
    reason: str | None = None  # 부를 수 없는 이유


_PATH_OK = re.compile(r"^/[A-Za-z0-9/_.\-{}:]*$")
_TEMPLATED = re.compile(r"\{[^/]*\}|/:[A-Za-z_]")
MAX_PATH = 100
MAX_ENDPOINTS = 30


@dataclass
class Scope:
    """이번 점검에서 도구가 닿을 수 있는 범위. service가 넘긴 요약으로 만든다."""

    assets: dict[str, Asset]
    base_findings: list[dict] = field(default_factory=list)  # {"asset_id", "check_id", "situation"}
    endpoints: dict[str, Endpoint] = field(default_factory=dict)

    @classmethod
    def from_summary(cls, summary: dict) -> "Scope":
        assets = {}
        for a in summary.get("assets") or []:
            asset = Asset(a["asset_id"], a["host"].lower(), a.get("alias") or a["host"],
                          tuple(a.get("tags") or ()), int(a.get("importance") or 3))
            assets[asset.asset_id] = asset
        findings = [{"asset_id": f["asset_id"], "check_id": f["check_id"], "situation": f.get("situation")}
                    for f in summary.get("findings") or [] if f.get("asset_id") in assets]
        return cls(assets=assets, base_findings=findings)

    def add_endpoint(self, asset_id: str, method: str, path: str) -> Endpoint | None:
        """핸들러가 찾은 엔드포인트를 등록하고 ID를 붙인다. 범위 밖·이상한 경로는 None.

        경로는 대상 서버의 응답에서 나온 값이라 LLM에 보내기 전에 글자와 길이를 제한한다.
        쿼리 문자열은 뗀다. 같은 (자산, 메서드, 경로)는 같은 엔드포인트를 돌려준다.
        """
        if asset_id not in self.assets:
            return None
        method = method.upper()
        path = path.split("?", 1)[0].split("#", 1)[0]
        if len(path) > MAX_PATH or not _PATH_OK.match(path):
            return None
        for e in self.endpoints.values():
            if (e.asset_id, e.method, e.path) == (asset_id, method, path):
                return e
        if len(self.endpoints) >= MAX_ENDPOINTS:
            return None
        reason = None
        if method != "GET":
            reason = "조회형(GET) 엔드포인트가 아님"
        elif _TEMPLATED.search(path):
            reason = "경로에 번호 변수가 있어 호출하지 않음(번호를 바꿔 가며 부르지 않는다)"
        e = Endpoint(f"E-{len(self.endpoints) + 1:02d}", asset_id, method, path, reason is None, reason)
        self.endpoints[e.endpoint_id] = e
        return e

    def endpoints_of(self, asset_id: str | None = None) -> list[dict]:
        return [{"endpoint_id": e.endpoint_id, "asset_id": e.asset_id, "method": e.method, "path": e.path,
                 "callable": e.callable}
                for e in self.endpoints.values() if asset_id is None or e.asset_id == asset_id]


# ==================================================================== 핸들러와 결과

@dataclass
class ToolResult:
    """핸들러가 돌려주는 값. data는 LLM에 그대로 가므로 발견 ID·상태·가린 증거만 담는다(응답 원문 금지)."""

    data: dict
    summary: str  # 감사 기록에 남길 한 줄


Handler = Callable[[ToolArgs, Scope], Awaitable[ToolResult]]
Audit = Callable[..., None]  # EngineContext.audit과 같은 시그니처


class Rejected(Exception):
    """가드 거부. 메시지가 거부 사유다."""


MAX_RESULT_CHARS = 1200  # 도구 결과 하나가 문맥을 다 먹지 않게 자른다


class Guard:
    """에이전트 하나의 도구 호출을 거르고 실행한다. 점검 1회의 추가 점검 단계마다 하나씩 만든다."""

    def __init__(self, agent: str, scope: Scope, budget: Budget, audit: Audit,
                 handlers: dict[str, Handler] | None = None):
        self.agent = agent
        self.scope = scope
        self.budget = budget
        self.audit = audit
        self.handlers: dict[str, Handler] = {"list_assets": self._list_assets, "finish_scan": self._finish}
        self.handlers.update(handlers or {})
        self.finished: str | None = None  # finish_scan의 reason
        self.calls = 0  # 이 가드를 거친 호출 수(거부·중복 포함)
        self._cache: dict[str, dict] = {}

    # ---------------------------------------------------------------- 공개

    def specs(self) -> list[ToolSpec]:
        """이 에이전트가 쓸 수 있는 도구. 핸들러가 없는 도구는 보여 주지도 않는다."""
        return [t for t in TOOLS.values() if t.agent == self.agent and t.name in self.handlers]

    def tools_for_llm(self) -> list[dict]:
        return [t.schema() for t in self.specs()]

    @property
    def exhausted(self) -> bool:
        return self.budget.tool_calls_used >= self.budget.tool_calls_limit

    @property
    def done(self) -> bool:
        return self.finished is not None or self.exhausted

    async def call(self, name: str, raw_args: str | dict | None, *, actor: str | None = None) -> dict:
        """도구 하나를 부른다. 돌려주는 dict는 LLM에 tool 메시지로 그대로 보낸다.

        actor는 감사 기록의 주체다. LLM 호출이면 에이전트 이름, 코드가 부르는 보충 점검이면 "system".
        ScanStopped(중지 요청·제한 시간)는 잡지 않고 올려 보낸다.
        """
        actor = actor or self.agent
        self.budget.check()
        logged_args: dict = _loggable(raw_args)
        try:
            if self.exhausted:
                raise Rejected(f"도구 호출 예산({self.budget.tool_calls_limit}회)을 다 썼음")
            self.budget.tool_calls_used += 1
            self.calls += 1
            spec = self._allowed(name)
            args = self._parse(spec, raw_args)
            logged_args = args.model_dump()
            self._in_scope(args)
            if spec.sends_requests and self.budget.requests_used >= self.budget.requests_limit:
                raise Rejected(f"요청 예산({self.budget.requests_limit}건)을 다 썼음")
        except Rejected as e:
            self.audit(actor, name, logged_args, rejected=True, reject_reason=str(e))
            return {"status": "rejected", "reason": str(e)}

        key = f"{name}|{json.dumps(logged_args, sort_keys=True, ensure_ascii=False)}"
        if key in self._cache and name != "list_assets":  # 목록은 엔드포인트가 늘면 바뀐다
            self.audit(actor, name, logged_args, "같은 호출이라 저장된 결과를 돌려줌")
            return {**self._cache[key], "cached": True}

        try:
            result = await self.handlers[name](args, self.scope)
        except ScanStopped:
            raise
        except Exception as e:  # 핸들러 오류는 LLM에 이유만 알리고 점검은 계속한다
            log.exception("도구 %s 실행 실패", name)
            self.audit(actor, name, logged_args, f"실행 실패: {type(e).__name__}")
            return {"status": "error", "reason": "도구 실행 중 오류가 났음"}

        data = _fit(result.data)
        self._cache[key] = data
        self.audit(actor, name, logged_args, result.summary)
        return data

    # ---------------------------------------------------------------- 거르기

    def _allowed(self, name: str) -> ToolSpec:
        spec = TOOLS.get(name)
        if spec is None:
            raise Rejected(f"없는 도구 {name!r}")
        if spec.agent != self.agent:
            raise Rejected(f"{self.agent} 에이전트에 허용되지 않은 도구")
        if name not in self.handlers:
            raise Rejected("아직 사용할 수 없는 도구")
        return spec

    @staticmethod
    def _parse(spec: ToolSpec, raw_args: str | dict | None) -> ToolArgs:
        if raw_args is None or raw_args == "":
            raw_args = {}
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except ValueError:
                raise Rejected("인자가 JSON이 아님") from None
        if not isinstance(raw_args, dict):
            raise Rejected("인자는 JSON 객체여야 함")
        try:
            return spec.args.model_validate(raw_args)
        except ValidationError as e:
            parts = [f"{'.'.join(str(p) for p in err['loc']) or '인자'}: {err['msg']}" for err in e.errors()[:3]]
            raise Rejected("인자가 스키마에 맞지 않음 (" + "; ".join(parts) + ")") from None

    def _in_scope(self, args: ToolArgs) -> None:
        asset_id = getattr(args, "asset_id", None)
        if asset_id is not None and asset_id not in self.scope.assets:
            raise Rejected(f"소유권이 확인된 자산이 아님: {asset_id}")
        endpoint_id = getattr(args, "endpoint_id", None)
        if endpoint_id is not None:
            e = self.scope.endpoints.get(endpoint_id)
            if e is None:
                raise Rejected(f"찾은 적 없는 엔드포인트: {endpoint_id}")
            if e.asset_id != asset_id:
                raise Rejected(f"{endpoint_id}는 {asset_id}의 엔드포인트가 아님")
            if not e.callable:
                raise Rejected(e.reason or "호출할 수 없는 엔드포인트")

    # ---------------------------------------------------------------- 기본 핸들러

    async def _list_assets(self, args: ToolArgs, scope: Scope) -> ToolResult:
        checks: dict[str, list[int]] = {}
        for f in scope.base_findings:
            checks.setdefault(f["asset_id"], []).append(f["check_id"])
        assets = [{"asset_id": a.asset_id, "alias": a.alias, "tags": list(a.tags), "importance": a.importance,
                   "base_findings": sorted(set(checks.get(a.asset_id, [])))}
                  for a in scope.assets.values()]
        return ToolResult({"status": "ok", "assets": assets, "endpoints": scope.endpoints_of()},
                          f"자산 {len(assets)}개, 엔드포인트 {len(scope.endpoints)}개")

    async def _finish(self, args: ToolArgs, scope: Scope) -> ToolResult:
        self.finished = args.reason  # type: ignore[attr-defined]
        return ToolResult({"status": "ok"}, f"추가 점검 종료: {self.finished}")


def _loggable(raw: str | dict | None) -> dict:
    """거부된 호출의 인자도 감사 기록에 남긴다. 너무 긴 값은 자른다."""
    if isinstance(raw, dict):
        return {str(k)[:40]: (v[:100] if isinstance(v, str) else v) for k, v in list(raw.items())[:5]}
    if isinstance(raw, str) and raw:
        try:
            obj = json.loads(raw)
        except ValueError:
            return {"raw": raw[:200]}
        return _loggable(obj) if isinstance(obj, dict) else {"raw": raw[:200]}
    return {}


def _fit(data: dict) -> dict:
    """결과가 길면 목록을 줄여 MAX_RESULT_CHARS 안에 맞춘다."""
    if len(json.dumps(data, ensure_ascii=False)) <= MAX_RESULT_CHARS:
        return data
    out = {**data, "truncated": True}  # 표시까지 넣은 길이로 잰다
    for k, v in data.items():
        if isinstance(v, list):
            while v and len(json.dumps({**out, k: v}, ensure_ascii=False)) > MAX_RESULT_CHARS:
                v = v[:-1]
            out[k] = v
    return out
