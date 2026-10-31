"""Attack·Defense 에이전트 연결 지점(담당: 김강현).

API는 이 모듈의 함수만 부른다. 지금은 LLM 상태 확인만 실제로 하고, 나머지는 None을 돌려줘
API가 기본 가이드(FR-11)로 동작한다. 에이전트를 붙일 때 아래 함수의 몸통을 채우면 된다.

- run_attack: 점검의 'agent' 단계(추가 점검). 엔진 도구를 가드 층을 거쳐 호출한다
- write_report: 오늘 할 일 3가지의 쉬운 설명(FR-07)과 근거 검증 결과(FR-08)
- answer_question: 담당자 질의응답(FR-12)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..config import Settings
from ..engine.base import EngineContext


class LlmClient:
    """vLLM(OpenAI 호환) 엔드포인트. 주소는 A2D_LLM_BASE_URL 하나로 바꾼다."""

    def __init__(self, settings: Settings):
        self.base = settings.llm_base_url
        self.key = settings.llm_api_key
        self.model = settings.llm_model
        self._status: tuple[float, str] = (0.0, "down")

    @property
    def configured(self) -> bool:
        return bool(self.base)

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.key}"} if self.key else {}

    async def status(self) -> str:
        """'up' 또는 'down'. 10초 동안 결과를 재사용한다."""
        if not self.configured:
            return "down"
        checked, value = self._status
        if time.monotonic() - checked < 10:
            return value
        try:
            async with httpx.AsyncClient(timeout=2.0) as c:
                r = await c.get(f"{self.base}/models", headers=self.headers())
            value = "up" if r.status_code == 200 else "down"
        except httpx.HTTPError:
            value = "down"
        self._status = (time.monotonic(), value)
        return value


@dataclass
class ReportDraft:
    """write_report의 결과. items는 API 명세 8장 report.items와 같은 형식이다."""

    items: list[dict]
    passed: int
    total: int


async def run_attack(llm: LlmClient, ctx: EngineContext, summary: dict) -> None:
    """추가 점검. summary에는 자산 ID·태그·기본 점검 결과 요약만 들어 있다(응답 원문 없음)."""
    return None


async def write_report(llm: LlmClient, tasks: list[dict], template: list[dict]) -> ReportDraft | None:
    """오늘 할 일 3가지(tasks)를 쉬운 말로 설명한다.

    None을 돌려주면 template(기본 가이드)을 그대로 쓴다. 근거 검증에 두 번 실패해도 None을 돌려준다.
    """
    return None


async def answer_question(llm: LlmClient, question: str, findings: list[dict]) -> dict | None:
    """{"answer", "finding_ids", "verification": {"passed"}}를 돌려준다. None이면 503 LLM_UNAVAILABLE."""
    return None
