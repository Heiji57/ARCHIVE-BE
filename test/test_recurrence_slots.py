"""
반복 규칙(day/week/month/year + weekdays/month_week) 슬롯 생성·RRULE 변환·요청 검증·
가상 인스턴스 series_rule 노출을 검증한다.

슬롯 의미는 RFC 5545 RRULE 과 같다 — Google Calendar 로 push 되는 RRULE 과 서버가
만드는 가상 인스턴스가 정확히 같은 날짜 집합이어야 중복/누락 일정이 생기지 않는다.

실행:
    PYTHONPATH=src pytest test/test_recurrence_slots.py
"""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.utils.recurrence import generate_slots_from, make_virtual, rule_to_rrule
from app.todo.presentation.requests.requests import RecurrenceRuleRequest
from app.todo.presentation.responses.responses import TodoResponse

# ── day (기존 동작 유지) ──────────────────────────────────────────────────────────

def test_day_interval_and_until() -> None:
    rule = RecurrenceRule(unit="day", interval=2, until="2026-10-09")
    assert generate_slots_from(rule, "2026-10-01", "2026-10-01", "2026-10-31") == [
        "2026-10-01", "2026-10-03", "2026-10-05", "2026-10-07", "2026-10-09",
    ]


def test_day_range_starts_after_series_start() -> None:
    rule = RecurrenceRule(unit="day", interval=3)
    assert generate_slots_from(rule, "2026-10-01", "2026-10-05", "2026-10-12") == [
        "2026-10-07", "2026-10-10",
    ]


# ── week ─────────────────────────────────────────────────────────────────────────

def test_week_without_weekdays_uses_start_weekday() -> None:
    # 기존 데이터(weekdays 없음) 하위 호환 — 2026-10-07 은 수요일.
    rule = RecurrenceRule(unit="week", interval=1)
    assert generate_slots_from(rule, "2026-10-07", "2026-10-01", "2026-10-31") == [
        "2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28",
    ]


def test_week_multiple_weekdays() -> None:
    # 월(0)·수(2)·금(4), 시작 2026-10-07(수) — 같은 주의 월(10-05)은 시작 전이라 제외.
    rule = RecurrenceRule(unit="week", interval=1, weekdays=(0, 2, 4))
    assert generate_slots_from(rule, "2026-10-07", "2026-10-01", "2026-10-14") == [
        "2026-10-07", "2026-10-09", "2026-10-12", "2026-10-14",
    ]


def test_week_biweekly_weekdays_anchor_on_start_week() -> None:
    # 격주 화(1)·목(3). 시작 주(10-05 주) → 10-19 주 → 11-02 주.
    rule = RecurrenceRule(unit="week", interval=2, weekdays=(1, 3))
    assert generate_slots_from(rule, "2026-10-06", "2026-10-01", "2026-11-05") == [
        "2026-10-06", "2026-10-08", "2026-10-20", "2026-10-22", "2026-11-03", "2026-11-05",
    ]


def test_week_start_not_in_weekdays_is_still_first_occurrence() -> None:
    # RFC 5545: DTSTART 는 항상 첫 회차. 시작 수(2), 반복 요일 월(0)만.
    rule = RecurrenceRule(unit="week", interval=1, weekdays=(0,))
    assert generate_slots_from(rule, "2026-10-07", "2026-10-01", "2026-10-20") == [
        "2026-10-07", "2026-10-12", "2026-10-19",
    ]


def test_weekdays_preset_mon_to_fri() -> None:
    rule = RecurrenceRule(unit="week", interval=1, weekdays=(0, 1, 2, 3, 4))
    assert generate_slots_from(rule, "2026-10-09", "2026-10-09", "2026-10-14") == [
        "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14",
    ]


# ── month ────────────────────────────────────────────────────────────────────────

def test_month_first_wednesday() -> None:
    rule = RecurrenceRule(unit="month", interval=1, month_week=1)
    assert generate_slots_from(rule, "2026-10-07", "2026-10-01", "2027-01-31") == [
        "2026-10-07", "2026-11-04", "2026-12-02", "2027-01-06",
    ]


def test_month_last_wednesday() -> None:
    rule = RecurrenceRule(unit="month", interval=1, month_week=-1)
    assert generate_slots_from(rule, "2026-10-28", "2026-10-01", "2027-01-31") == [
        "2026-10-28", "2026-11-25", "2026-12-30", "2027-01-27",
    ]


def test_month_every_two_months_second_tuesday() -> None:
    rule = RecurrenceRule(unit="month", interval=2, month_week=2)
    assert generate_slots_from(rule, "2026-10-13", "2026-10-01", "2027-03-31") == [
        "2026-10-13", "2026-12-08", "2027-02-09",
    ]


def test_month_range_jump_far_from_start() -> None:
    rule = RecurrenceRule(unit="month", interval=1, month_week=1)
    assert generate_slots_from(rule, "2020-01-01", "2026-10-01", "2026-11-30") == [
        "2026-10-07", "2026-11-04",
    ]


def test_month_until_inclusive() -> None:
    rule = RecurrenceRule(unit="month", interval=1, month_week=1, until="2026-12-02")
    assert generate_slots_from(rule, "2026-10-07", "2026-10-01", "2027-03-31") == [
        "2026-10-07", "2026-11-04", "2026-12-02",
    ]


# ── year ─────────────────────────────────────────────────────────────────────────

def test_year_same_month_day() -> None:
    rule = RecurrenceRule(unit="year", interval=1)
    assert generate_slots_from(rule, "2026-10-07", "2026-01-01", "2028-12-31") == [
        "2026-10-07", "2027-10-07", "2028-10-07",
    ]


def test_year_feb_29_only_on_leap_years() -> None:
    rule = RecurrenceRule(unit="year", interval=1)
    assert generate_slots_from(rule, "2024-02-29", "2024-01-01", "2032-12-31") == [
        "2024-02-29", "2028-02-29", "2032-02-29",
    ]


def test_year_interval_and_range_jump() -> None:
    rule = RecurrenceRule(unit="year", interval=2)
    assert generate_slots_from(rule, "2000-03-01", "2025-01-01", "2029-12-31") == [
        "2026-03-01", "2028-03-01",
    ]


def test_slots_empty_when_start_after_range() -> None:
    rule = RecurrenceRule(unit="month", interval=1, month_week=1)
    assert generate_slots_from(rule, "2027-01-06", "2026-10-01", "2026-12-31") == []


# ── RRULE ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (RecurrenceRule(unit="day", interval=1), "RRULE:FREQ=DAILY;INTERVAL=1"),
        (RecurrenceRule(unit="week", interval=2), "RRULE:FREQ=WEEKLY;INTERVAL=2"),
        (
            RecurrenceRule(unit="week", interval=1, weekdays=(4, 0, 2)),
            "RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,WE,FR",
        ),
        (
            RecurrenceRule(unit="month", interval=1, month_week=1),
            "RRULE:FREQ=MONTHLY;INTERVAL=1;BYDAY=1WE",
        ),
        (
            RecurrenceRule(unit="month", interval=3, month_week=-1, until="2027-06-30"),
            "RRULE:FREQ=MONTHLY;INTERVAL=3;BYDAY=-1WE;UNTIL=20270630",
        ),
        (RecurrenceRule(unit="year", interval=1), "RRULE:FREQ=YEARLY;INTERVAL=1"),
    ],
)
def test_rule_to_rrule(rule: RecurrenceRule, expected: str) -> None:
    # 2026-10-07 = 수요일 — 월간 BYDAY 요일은 시작일에서 나온다.
    assert rule_to_rrule(rule, "2026-10-07") == expected


# ── 요청 검증 ────────────────────────────────────────────────────────────────────

def test_request_accepts_month_and_year() -> None:
    month = RecurrenceRuleRequest(unit="month", interval=1, month_week=-1).to_domain()
    assert month == RecurrenceRule(unit="month", interval=1, month_week=-1)
    week = RecurrenceRuleRequest(unit="week", interval=1, weekdays=[4, 0, 2]).to_domain()
    assert week.weekdays == (0, 2, 4)
    assert RecurrenceRuleRequest(unit="year", interval=1).to_domain().unit == "year"


@pytest.mark.parametrize(
    "payload",
    [
        {"unit": "month", "interval": 1},  # month_week 필수
        {"unit": "month", "interval": 1, "month_week": 5},
        {"unit": "day", "interval": 1, "month_week": 1},
        {"unit": "day", "interval": 1, "weekdays": [0]},
        {"unit": "week", "interval": 1, "weekdays": []},
        {"unit": "week", "interval": 1, "weekdays": [7]},
        {"unit": "week", "interval": 1, "weekdays": [1, 1]},
        {"unit": "hour", "interval": 1},
    ],
)
def test_request_rejects_invalid_combinations(payload: dict) -> None:
    with pytest.raises(ValidationError):
        RecurrenceRuleRequest(**payload)


# ── 가상 인스턴스 series_rule ────────────────────────────────────────────────────

def _base(rule: RecurrenceRule) -> Todo:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    return Todo(
        id="todo_base",
        user_id="u1",
        title="주간 회의",
        status=TaskStatus.NOT_START,
        date_key="2026-10-07",
        created_at=now,
        updated_at=now,
        recurrence_rule=rule,
    )


def test_virtual_instance_exposes_series_rule_but_not_recurrence_rule() -> None:
    rule = RecurrenceRule(unit="month", interval=1, month_week=1)
    virtual = make_virtual(_base(rule), "2026-11-04")
    assert virtual.recurrence_rule is None  # base 판별(is_series_base) 의미는 그대로
    assert virtual.series_rule == rule

    res = TodoResponse.from_entity(virtual)
    assert res.recurrence_rule is None
    assert res.series_rule is not None
    assert res.series_rule.unit == "month"
    assert res.series_rule.month_week == 1


def test_non_virtual_response_has_no_series_rule() -> None:
    res = TodoResponse.from_entity(_base(RecurrenceRule(unit="week", interval=1, weekdays=(0, 2))))
    assert res.series_rule is None
    assert res.recurrence_rule is not None
    assert res.recurrence_rule.weekdays == [0, 2]


def test_week_biweekly_multi_weekday_range_starts_mid_cycle() -> None:
    # 격주 월(0)·목(3), 시작 2026-10-05(월). 활성 주: 10-05, 10-19, 11-02 …
    # 범위가 비활성 주(10-12 주) 중간에서 시작해도 다음 활성 주부터 정확히 이어져야 한다.
    rule = RecurrenceRule(unit="week", interval=2, weekdays=(0, 3))
    assert generate_slots_from(rule, "2026-10-05", "2026-10-14", "2026-11-05") == [
        "2026-10-19", "2026-10-22", "2026-11-02", "2026-11-05",
    ]
    # 활성 주 중간(목요일 전)에서 시작.
    assert generate_slots_from(rule, "2026-10-05", "2026-10-20", "2026-10-31") == [
        "2026-10-22",
    ]


# ── JSONB 영속화 왕복 ────────────────────────────────────────────────────────────

def test_rule_jsonb_round_trip_and_legacy_rows() -> None:
    from app.todo.infrastructure.persistence.repositories.todo_repo import (
        _dict_to_rule,
        _rule_to_dict,
    )

    for rule in [
        RecurrenceRule(unit="day", interval=1),
        RecurrenceRule(unit="week", interval=2, weekdays=(0, 2), until="2027-01-01"),
        RecurrenceRule(unit="month", interval=1, month_week=-1),
        RecurrenceRule(unit="year", interval=3),
    ]:
        assert _dict_to_rule(_rule_to_dict(rule)) == rule

    # 기존 day/week 규칙은 JSON 모양이 그대로여야 한다(신규 키 없음).
    assert _rule_to_dict(RecurrenceRule(unit="week", interval=1)) == {
        "unit": "week", "interval": 1, "until": None,
    }
    # 신규 키가 없는 기존 row 도 그대로 로드된다.
    assert _dict_to_rule({"unit": "day", "interval": 2, "until": None}) == RecurrenceRule(
        unit="day", interval=2
    )


# ── RRULE ↔ 슬롯 교차 검증 (GCal 과 같은 날짜 집합) ───────────────────────────────

def test_slots_match_rrule_expansion_randomized() -> None:
    """rule_to_rrule 문자열을 dateutil(RFC 5545 구현)로 펼친 결과와 generate_slots_from 이
    무작위 규칙·시작일·조회 범위에서 항상 같아야 한다 — GCal 에 push 된 RRULE 과 서버
    가상 인스턴스가 어긋나면 중복/누락 일정이 생긴다."""
    import random
    from datetime import date, timedelta

    rrule_mod = pytest.importorskip("dateutil.rrule")

    rng = random.Random(20261005)
    for _ in range(400):
        unit = rng.choice(["day", "week", "month", "year"])
        interval = rng.choice([1, 1, 2, 3])
        start = date(2024, 1, 1) + timedelta(days=rng.randrange(0, 900))
        weekdays: tuple[int, ...] | None = None
        month_week: int | None = None
        if unit == "week" and rng.random() < 0.7:
            weekdays = tuple(sorted(rng.sample(range(7), rng.randint(1, 4))))
        if unit == "month":
            nth = (start.day - 1) // 7 + 1
            month_week = -1 if nth == 5 else rng.choice([nth, -1] if start.day + 7 > 28 else [nth])
            # -1 은 시작일이 실제로 마지막 주일 때만 의미가 있다 (FE 도 그때만 제공).
            if month_week == -1 and (start + timedelta(days=7)).month == start.month:
                month_week = nth
        until = None
        if rng.random() < 0.3:
            until = (start + timedelta(days=rng.randrange(0, 1200))).isoformat()
        rule = RecurrenceRule(
            unit=unit, interval=interval, until=until, weekdays=weekdays, month_week=month_week
        )

        r_start = start + timedelta(days=rng.randrange(-60, 900))
        r_end = r_start + timedelta(days=rng.randrange(0, 500))

        rrule_text = rule_to_rrule(rule, start.isoformat()).removeprefix("RRULE:")
        expanded = rrule_mod.rrulestr(
            rrule_text, dtstart=datetime(start.year, start.month, start.day)
        )
        expected_set = {
            d.date().isoformat()
            for d in expanded.between(
                datetime(r_start.year, r_start.month, r_start.day),
                datetime(r_end.year, r_end.month, r_end.day),
                inc=True,
            )
        }
        # RFC 5545: DTSTART 는 규칙과 맞지 않아도 첫 회차 (dateutil 은 이를 넣지 않음).
        start_alive = until is None or start.isoformat() <= until
        if r_start <= start <= r_end and start_alive:
            expected_set.add(start.isoformat())
        expected = sorted(expected_set)
        actual = generate_slots_from(
            rule, start.isoformat(), r_start.isoformat(), r_end.isoformat()
        )
        assert actual == expected, (rule, start, r_start, r_end)
