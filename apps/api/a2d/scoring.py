"""위험·안전 점수 계산(docs/A2D_점검점수설계.md 2장). 계산은 모두 코드가 하고 LLM은 관여하지 않는다.

반올림은 계산 끝에 한 번만 한다. 그래서 내부에서는 반올림 전 값(raw)을 쓰고,
화면에 내려줄 때만 round_half_up으로 정수로 바꾼다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

CONFIDENCE_FACTOR = {"confirmed": 1.0, "likely": 0.8, "needs_review": 0.6}


def round_half_up(v: float) -> int:
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def risk_raw(e: int, x: int, d: int, c: int, confidence: str) -> float:
    return 100 * ((e * x * d * c) ** 0.25 - 1) / 4 * CONFIDENCE_FACTOR[confidence]


def severity(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def risk_formula(e: int, x: int, d: int, c: int, confidence: str) -> str:
    k = CONFIDENCE_FACTOR[confidence]
    score = round_half_up(risk_raw(e, x, d, c, confidence))
    return f"100 × (({e} × {x} × {d} × {c})^(1/4) − 1) ÷ 4 × {k} = {score}"


def org_risk_raw(scores: Iterable[float]) -> float:
    s = sorted(scores, reverse=True)
    if not s:
        return 0.0
    rest = (s[1:6] + [0.0] * 5)[:5]
    return 0.7 * s[0] + 0.3 * sum(rest) / 5


def safety_from_raw(scores: Iterable[float]) -> int:
    return round_half_up(100 - org_risk_raw(scores))


def grade(safety: int) -> str:
    if safety >= 90:
        return "A"
    if safety >= 72:
        return "B"
    if safety >= 58:
        return "C"
    if safety >= 44:
        return "D"
    return "F"


def org_formula(scores: Sequence[float]) -> str:
    s = sorted(scores, reverse=True)
    if not s:
        return "발견 없음 = 0"
    top = round_half_up(s[0])
    rest = [round_half_up(v) for v in s[1:6]]
    rest_txt = " + ".join(str(v) for v in rest) if rest else "0"
    total = round_half_up(org_risk_raw(s))
    return f"0.7 × {top} + 0.3 × ({rest_txt}) ÷ 5 = {total}"


@dataclass
class Scored:
    """점수 계산에 필요한 발견의 최소 정보."""

    finding_id: str
    raw: float
    fix_minutes: int


@dataclass
class TaskPick:
    finding_id: str
    safety_after: int
    grade_after: str


def pick_today_tasks(findings: Sequence[Scored], n: int = 3) -> list[TaskPick]:
    """상세설계 2절 '오늘 할 일 3가지 고르기'.

    남은 발견마다 고쳤을 때의 안전 점수 상승을 계산해 가장 큰 것을 고른다.
    같으면 발견 점수가 높은 것, 그다음 조치 시간이 짧은 것, 마지막으로 발견 ID 순이다.
    """
    remaining = [f for f in findings if f.raw > 0]
    picks: list[TaskPick] = []
    while remaining and len(picks) < n:
        base = 100 - org_risk_raw(f.raw for f in remaining)
        best = None
        best_key = None
        for f in remaining:
            after = 100 - org_risk_raw(g.raw for g in remaining if g is not f)
            key = (-(after - base), -f.raw, f.fix_minutes, f.finding_id)
            # 부동소수 오차로 동점이 갈리지 않게 상승 폭은 소수 6자리에서 자른다.
            key = (round(key[0], 6),) + key[1:]
            if best_key is None or key < best_key:
                best, best_key = f, key
        assert best is not None
        remaining = [g for g in remaining if g is not best]
        safety_after = round_half_up(100 - org_risk_raw(g.raw for g in remaining))
        picks.append(TaskPick(best.finding_id, safety_after, grade(safety_after)))
    return picks
