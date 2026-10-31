"""점검·점수 설계 2.3·2.4와 상세설계 2절 계산 예시가 그대로 나오는지 확인한다(FR-05 수용 기준)."""

import pytest

from a2d.catalog import FIX_MINUTES, GUIDES, SITUATIONS
from a2d.scoring import Scored, grade, pick_today_tasks, risk_raw, round_half_up, safety_from_raw


def f(e, x, d, c, conf="confirmed"):
    return risk_raw(e, x, d, c, conf)


# 2.3 항목별 기본값 (C는 표의 대표값, 위험 점수)
TABLE_2_3 = [
    (6, "dangling", 4, 65), (8, "confirmed", 5, 100), (8, "unknown_format", 5, 60), (9, "env", 5, 100),
    (9, "git", 5, 93), (10, "basic", 3, 72), (10, "sensitive", 3, 85), (11, "basic", 4, 58),
    (12, "secret", 5, 100), (13, "basic", 4, 38), (14, "listing", 5, 93), (14, "sensitive", 5, 100),
    (16, "pii", 5, 100), (16, "data", 5, 74), (17, "basic", 5, 54), (18, "basic", 4, 73),
    (19, "basic", 3, 52), (19, "debug", 3, 67), (20, "env", 4, 87), (20, "status", 4, 73),
    (21, "any_origin", 5, 53), (21, "loose_match", 5, 46), (23, "kev", 4, 69), (23, "cvss9", 4, 65),
    (23, "cvss7", 4, 59), (23, "cvss_low", 4, 51), (25, "server", 4, 46), (26, "basic", 4, 48),
    (26, "login", 5, 58), (27, "basic", 4, 34), (28, "expired", 5, 74), (28, "expiring14", 5, 62),
    (28, "expiring30", 5, 54), (28, "invalid", 4, 48), (30, "basic", 4, 30), (31, "login", 5, 52),
    (31, "other", 4, 30), (32, "none", 5, 74), (32, "weak_dmarc", 5, 69), (32, "weak_spf", 5, 31),
    (33, "expired", 5, 100), (33, "expiring30", 5, 74), (33, "expiring90", 5, 59), (34, "pii", 5, 100),
    (34, "data", 5, 74), (34, "firebase", 5, 75),
]


@pytest.mark.parametrize("check_id,key,c,expected", TABLE_2_3)
def test_situation_defaults(check_id, key, c, expected):
    s = SITUATIONS[(check_id, key)]
    if s.c_fixed is not None:
        assert s.c_fixed == c
    assert round_half_up(risk_raw(s.e, s.x, s.d, c, s.confidence)) == expected


# 2.4 시나리오 검증
SCENARIOS = [
    ([f(5, 5, 5, 5)], 30, "F"),  # 백업 파일 하나만
    ([f(3, 2, 1, 4)], 79, "B"),  # 보안 헤더만
    ([f(5, 5, 5, 5), f(5, 3, 4, 4)], 26, "F"),  # 인증 없는 API + 관리자 페이지
    ([f(5, 5, 5, 5)], 30, "F"),  # RLS 꺼짐(#34 pii)
    ([f(5, 2, 5, 5)], 48, "D"),  # 도메인 만료 20일
    # 낮음 3개(전환 없음·헤더·기타 쿠키). 2.4 표는 73이지만, 발견 점수를 먼저 반올림하지 않는 2.1 규칙으로는 72다(등급 B 같음)
    ([f(2, 2, 2, 4), f(3, 2, 1, 4), f(3, 2, 1, 4)], 72, "B"),
    # 2.4 표는 입력 발견을 밝히지 않아 같은 점수의 발견으로 공식만 확인한다
    ([36.0] * 6, 64, "C"),  # 낮음 6개
    ([56.82] * 4, 50, "D"),  # 중간 4개
    ([f(5, 3, 4, 4)] + [f(5, 2, 3, 3)] * 3, 39, "F"),  # 높음 1 + 중간 3
]


@pytest.mark.parametrize("raws,safety,g", SCENARIOS)
def test_scenarios(raws, safety, g):
    assert safety_from_raw(raws) == safety
    assert grade(safety) == g


def test_design_example_today_tasks():
    """상세설계 2절 계산 예시: 12(F) → 27 → 40 → 50(D), 순서 #16 #8 #18."""
    fs = [
        Scored("F-16", f(5, 5, 5, 5), 60),
        Scored("F-8", f(5, 5, 5, 3), 10),
        Scored("F-18", f(5, 3, 4, 4), 30),
        Scored("F-23", f(5, 4, 4, 4, "likely"), 60),
        Scored("F-19", f(5, 2, 3, 3), 30),
        Scored("F-30", f(3, 2, 1, 4), 30),
    ]
    assert safety_from_raw(x.raw for x in fs) == 12
    picks = pick_today_tasks(fs)
    assert [p.finding_id for p in picks] == ["F-16", "F-8", "F-18"]
    assert [p.safety_after for p in picks] == [27, 40, 50]
    assert picks[-1].grade_after == "D"


def test_target_demo_preset():
    """target/README.md 기본 시연: 20 F → 30 F → 49 D → 100 A."""
    fs = [Scored("F-16", f(5, 5, 5, 5), 60), Scored("F-8", f(5, 5, 5, 4), 10), Scored("F-18", f(5, 3, 4, 4), 30)]
    assert safety_from_raw(x.raw for x in fs) == 20
    picks = pick_today_tasks(fs)
    assert [(p.finding_id, p.safety_after, p.grade_after) for p in picks] == [
        ("F-16", 30, "F"), ("F-8", 49, "D"), ("F-18", 100, "A")]


def test_tie_prefers_shorter_fix_time():
    """같은 점수면 조치 시간이 짧은 것이 먼저다(target README: www C=5일 때 #8이 #16보다 먼저)."""
    fs = [Scored("F-16", f(5, 5, 5, 5), 60), Scored("F-8", f(5, 5, 5, 5), 10)]
    assert pick_today_tasks(fs)[0].finding_id == "F-8"


def test_every_scored_situation_has_guide_and_fix_time():
    for (check_id, _), s in SITUATIONS.items():
        if not s.info:
            assert check_id in GUIDES
            assert check_id in FIX_MINUTES
