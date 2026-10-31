"""API와 점검 엔진 사이의 약속.

API(서비스 층)는 엔진이 무엇을 어떻게 점검하는지 모른다. 엔진은 아래 EngineContext로
진행 상태·자산·발견·감사 기록을 넘기기만 하고, 점수·발견 ID·오늘 할 일·조치 가이드는 API가 만든다.

실제 엔진은 Engine을 상속해 run()을 구현하고, A2D_ENGINE=패키지.모듈:클래스 로 바꿔 끼운다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from ..catalog import CHECKS, SITUATIONS


class ScanStopped(Exception):
    """중지 요청 또는 제한 시간 초과. 엔진은 잡지 말고 그대로 올려 보낸다."""


class EngineError(Exception):
    """점검을 끝낼 수 없음(DNS 무응답, 대상에 연결 불가 등). 점검은 실패로 끝나고 메시지가 화면에 그대로 보인다.

    발견 0건은 100점(A)이 되므로, 아무것도 보지 못한 점검을 '문제 없음'으로 끝내지 않으려고 쓴다.
    """


@dataclass
class Budget:
    requests_limit: int
    tool_calls_limit: int
    time_limit_sec: int
    requests_used: int = 0
    tool_calls_used: int = 0
    started: float = field(default_factory=time.monotonic)
    stop_requested: bool = False

    @property
    def elapsed(self) -> int:
        return int(time.monotonic() - self.started)

    @property
    def requests_exhausted(self) -> bool:
        """요청 상한을 다 썼는지. 상한이 0이면 제한이 없다(정확한 결과를 위해 기본값은 0)."""
        return self.requests_limit > 0 and self.requests_used >= self.requests_limit

    def check(self) -> None:
        if self.stop_requested:
            raise ScanStopped("중지 요청")
        if self.elapsed >= self.time_limit_sec:
            raise ScanStopped("제한 시간 초과")

    def to_api(self) -> dict:
        return {
            "requests_used": self.requests_used,
            "requests_limit": self.requests_limit,
            "tool_calls_used": self.tool_calls_used,
            "tool_calls_limit": self.tool_calls_limit,
            "elapsed_sec": self.elapsed,
            "time_limit_sec": self.time_limit_sec,
        }


@dataclass
class RawAsset:
    host: str
    alias: str
    url: str | None
    found_by: list[int]  # 자산 찾기 항목 번호(#1~#5)
    tags: list[str] = field(default_factory=list)
    importance: int = 3  # 자동 추정(점검·점수 설계 2.2)
    importance_rule: str | None = "일반 하위 서비스"
    components: list[dict] = field(default_factory=list)  # #24: {"name", "version", "eol"}
    tls_version: str | None = None


@dataclass
class RawFinding:
    host: str  # 어느 자산의 발견인가 (RawAsset.host)
    check_id: int
    situation: str  # catalog.SITUATIONS의 키. 예: (16, "pii")
    location: str  # 예: "GET https://api.example.com/v1/members/1024"
    evidence: str  # 마스킹된 발췌, 200자 이내 (NFR-05)
    cves: list[dict] = field(default_factory=list)  # #23만. {"id", "cvss", "kev"}

    def validate(self) -> None:
        if self.check_id not in CHECKS:
            raise ValueError(f"없는 점검 항목 #{self.check_id}")
        if (self.check_id, self.situation) not in SITUATIONS:
            raise ValueError(f"#{self.check_id}에 없는 상황 {self.situation!r}")
        if len(self.evidence) > 200:
            raise ValueError("증거는 200자 이내로 가려서 넘긴다")


@dataclass
class EngineContext:
    scan_id: str
    domain: str
    round: int  # 이 도메인의 몇 번째 점검인지(1부터)
    budget: Budget
    set_stage: Callable[[str, str, int, int], None]  # (status, 화면 표기, done, total)
    add_asset: Callable[[RawAsset], str]  # 자산 ID를 돌려준다
    add_finding: Callable[[RawFinding], tuple[str, str]]  # (발견 ID, 자산 ID)를 돌려준다
    audit: Callable[..., None]  # audit(actor, tool, args, result_summary=None, rejected=False, reject_reason=None)


class Engine:
    async def run(self, ctx: EngineContext) -> None:  # pragma: no cover - 인터페이스
        """자산 찾기(status=discovering)와 기본 점검(status=checking)을 돌린다.

        - 단계가 바뀔 때마다 ctx.set_stage를 부른다.
        - 오래 걸리는 일 사이사이 ctx.budget.check()를 불러 중지 요청을 받는다.
        - 응답 원문은 넘기지 않는다. 증거는 마스킹된 발췌만 넘긴다.
        """
        raise NotImplementedError
