"""시연 시나리오를 돌려주는 가짜 엔진. 실제 네트워크 요청은 하나도 보내지 않는다.

화면(apps/web) 개발과 API 시험용이다. fixtures/demo_engine.json의 rounds를 점검 순서대로 쓴다.
같은 도메인의 n번째 점검은 rounds[n-1]을 쓰고, 마지막 뒤로는 마지막 것을 반복한다.
기본 시나리오는 target/README.md의 시연 순서와 같다.
  1회차: #16 #8 #18 결함 → 안전 점수 20 (F)
  2회차: 세 가지를 고친 뒤 재점검 → 100 (A), 해결됨 3건
  3회차: 새 테스트 서버(test.) 열림 → new_asset 알림, #19 새 발견
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..config import API_ROOT
from .base import Engine, EngineContext, RawAsset, RawFinding

FIXTURE = API_ROOT / "fixtures" / "demo_engine.json"


def _fill(v, domain: str):
    if isinstance(v, str):
        return v.replace("{domain}", domain)
    if isinstance(v, list):
        return [_fill(x, domain) for x in v]
    if isinstance(v, dict):
        return {k: _fill(x, domain) for k, x in v.items()}
    return v


class FixtureEngine(Engine):
    def __init__(self, step_sec: float = 0.4, path: Path = FIXTURE):
        self.step = step_sec
        self.rounds = json.loads(path.read_text(encoding="utf-8"))["rounds"]

    async def _tick(self, ctx: EngineContext) -> None:
        ctx.budget.check()
        if self.step:
            await asyncio.sleep(self.step)
        ctx.budget.check()

    def _round(self, n: int) -> dict:
        """'same'은 1회차 자산 그대로, 'same+'는 1회차 자산에 extra_assets를 더한다."""
        r = dict(self.rounds[min(n, len(self.rounds)) - 1])
        if r["assets"] in ("same", "same+"):
            extra = r.get("extra_assets", []) if r["assets"] == "same+" else []
            r["assets"] = self.rounds[0]["assets"] + extra
        return r

    async def run(self, ctx: EngineContext) -> None:
        r = _fill(self._round(ctx.round), ctx.domain)
        assets = [RawAsset(**a) for a in r["assets"]]
        findings = [RawFinding(**f) for f in r["findings"]]

        ctx.set_stage("discovering", "자산 찾는 중", 0, len(assets))
        for i, a in enumerate(assets, 1):
            await self._tick(ctx)
            asset_id = ctx.add_asset(a)
            ctx.budget.requests_used += 2
            ctx.audit("system", "discover_assets", {"asset_id": asset_id}, f"자산 {a.alias} 확인")
            ctx.set_stage("discovering", "자산 찾는 중", i, len(assets))

        # 기본 점검: 자산마다 점검 도구 묶음을 한 번씩 돈다고 보고 단계를 센다.
        steps = [(a, tool) for a in assets for tool in ("check_paths", "check_tls_headers")]
        ctx.set_stage("checking", "기본 점검", 0, len(steps))
        for i, (a, step_tool) in enumerate(steps, 1):
            await self._tick(ctx)
            ctx.budget.requests_used += 4
            hits = [f for f in findings if f.host == a.host] if step_tool == "check_paths" else []
            for f in hits:
                finding_id, asset_id = ctx.add_finding(f)
                ctx.audit("system", TOOL_OF.get(f.check_id, "check_paths"), {"asset_id": asset_id},
                          f"발견 {finding_id} 기록")
            ctx.set_stage("checking", "기본 점검", i, len(steps))


# 점검 항목 → 상세설계 4절의 도구 이름(감사 기록 표시용)
TOOL_OF = {
    **{n: "check_paths" for n in (8, 9, 10, 11, 17, 18, 19, 20)},
    16: "check_unauth_api",
    21: "check_cors",
    **{n: "check_frontend_code" for n in (12, 13, 34)},
    **{n: "check_tls_headers" for n in (26, 27, 28, 30, 31)},
    **{n: "lookup_known_vulns" for n in (23, 25)},
}
