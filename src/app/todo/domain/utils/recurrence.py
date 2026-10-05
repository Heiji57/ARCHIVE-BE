"""반복 Todo 관련 순수 도메인 유틸리티.

- generate_slots_from: base event 의 RecurrenceRule 로부터 슬롯 날짜(YYYY-MM-DD) 시퀀스 생성.
- rule_to_rrule: RecurrenceRule → GCal RRULE 문자열 (generate_slots_from 과 같은 날짜 집합).
- make_virtual: 슬롯 날짜 + base 로부터 가상 Todo 인스턴스 생성.
- build_gcal_instance_id: GCal instance ID 계산 (base_event_id + originalStartTime UTC).
- compute_instance_start/end: 슬롯에 맞게 base 의 start/end_time 을 보정.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.shared.domain.utils.id import generate_id

if TYPE_CHECKING:
    from app.todo.domain.models.todo import RecurrenceRule, Todo


_RRULE_WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def generate_slots_from(
    rule: "RecurrenceRule",
    series_start: str,   # base.date_key (= RRULE DTSTART)
    range_start: str,    # 조회 범위 시작 (포함)
    range_end: str,      # 조회 범위 끝 (포함)
) -> list[str]:
    """rule 이 series_start 부터 만드는 회차 중 [range_start, range_end] 에 속하는 날짜를 반환.

    의미는 RFC 5545 RRULE 과 같다 — GCal 로 push 되는 RRULE(rule_to_rrule)과 같은 날짜
    집합이어야 중복/누락 일정이 생기지 않는다. series_start(DTSTART)는 규칙과 맞지 않아도
    항상 첫 회차다. 각 단위는 조회 범위 시작점으로 곧장 점프한 뒤 생성한다 — 시작일이 먼
    과거인 시리즈를 넓은 범위로 조회(stats range=all)해도 루프가 범위 크기에만 비례한다.
    """
    if rule is None:
        return []
    s_date = date.fromisoformat(series_start)
    r_start = date.fromisoformat(range_start)
    r_end = date.fromisoformat(range_end)
    if rule.until:
        r_end = min(r_end, date.fromisoformat(rule.until))
    if s_date > r_end or r_start > r_end:
        return []

    lo = max(s_date, r_start)
    if rule.unit == "day":
        slots = _day_slots(rule.interval, s_date, lo, r_end)
    elif rule.unit == "week":
        weekdays = rule.weekdays or (s_date.weekday(),)
        slots = _week_slots(rule.interval, weekdays, s_date, lo, r_end)
    elif rule.unit == "month":
        month_week = rule.month_week if rule.month_week is not None else _month_week_of(s_date)
        slots = _month_slots(rule.interval, month_week, s_date, lo, r_end)
    else:
        slots = _year_slots(rule.interval, s_date, lo, r_end)

    # DTSTART 는 항상 첫 회차 (맞춤 주간 반복에서 시작일 요일을 뺀 경우 등).
    if r_start <= s_date and (not slots or slots[0] != s_date):
        slots.insert(0, s_date)
    return [d.isoformat() for d in slots]


def _day_slots(interval: int, s_date: date, lo: date, hi: date) -> list[date]:
    steps = -(-(lo - s_date).days // interval)  # ceil
    current = s_date + timedelta(days=interval * steps)
    out: list[date] = []
    while current <= hi:
        out.append(current)
        current += timedelta(days=interval)
    return out


def _week_slots(
    interval: int, weekdays: tuple[int, ...], s_date: date, lo: date, hi: date
) -> list[date]:
    # 주 경계 = 월요일 (RRULE WKST=MO 기본값). 시작일이 속한 주가 0번째 활성 주.
    week0 = s_date - timedelta(days=s_date.weekday())
    period = timedelta(weeks=interval)
    lo_week = lo - timedelta(days=lo.weekday())
    k = (lo_week - week0).days // (7 * interval)  # floor — lo 가 속한 주기부터
    week_start = week0 + period * k
    out: list[date] = []
    while week_start <= hi:
        for wd in sorted(weekdays):
            d = week_start + timedelta(days=wd)
            if lo <= d <= hi:
                out.append(d)
        week_start += period
    return out


def _month_week_of(d: date) -> int:
    """d 가 그 달의 몇 번째 요일인지 (1~4). 5번째는 모든 달에 있지 않아 -1(마지막)."""
    n = (d.day - 1) // 7 + 1
    return -1 if n == 5 else n


def _nth_weekday(year: int, month: int, weekday: int, month_week: int) -> date | None:
    """year-month 의 month_week 번째(-1 = 마지막) weekday. 그 달에 없으면 None."""
    if month_week == -1:
        last = date(year, month, calendar.monthrange(year, month)[1])
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first = date(year, month, 1)
    d = first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (month_week - 1))
    return d if d.month == month else None


def _month_slots(
    interval: int, month_week: int, s_date: date, lo: date, hi: date
) -> list[date]:
    m0 = s_date.year * 12 + s_date.month - 1
    lo_idx = lo.year * 12 + lo.month - 1
    k = max(0, -(-(lo_idx - m0) // interval))  # ceil — lo 의 달 이후 첫 활성 달
    idx = m0 + interval * k
    out: list[date] = []
    while True:
        year, month = divmod(idx, 12)
        if date(year, month + 1, 1) > hi:
            break
        d = _nth_weekday(year, month + 1, s_date.weekday(), month_week)
        if d is not None and lo <= d <= hi:
            out.append(d)
        idx += interval
    return out


def _year_slots(interval: int, s_date: date, lo: date, hi: date) -> list[date]:
    k = max(0, -(-(lo.year - s_date.year) // interval))
    year = s_date.year + interval * k
    out: list[date] = []
    while date(year, 1, 1) <= hi:
        try:
            d = date(year, s_date.month, s_date.day)
        except ValueError:  # 2/29 시작 → 평년은 건너뜀 (RRULE 과 동일)
            year += interval
            continue
        if lo <= d <= hi:
            out.append(d)
        year += interval
    return out


def rule_to_rrule(rule: RecurrenceRule, series_start: str) -> str:
    """RecurrenceRule → Google RRULE 문자열. 월간 BYDAY 요일은 시작일(series_start)에서 나온다."""
    freq = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}[rule.unit]
    rrule = f"RRULE:FREQ={freq};INTERVAL={rule.interval}"
    if rule.unit == "week" and rule.weekdays:
        rrule += ";BYDAY=" + ",".join(_RRULE_WEEKDAYS[wd] for wd in sorted(rule.weekdays))
    elif rule.unit == "month":
        s_date = date.fromisoformat(series_start)
        month_week = rule.month_week if rule.month_week is not None else _month_week_of(s_date)
        rrule += f";BYDAY={month_week}{_RRULE_WEEKDAYS[s_date.weekday()]}"
    if rule.until:
        # GCal UNTIL 형식: YYYYMMDD (date-only)
        rrule += f";UNTIL={rule.until.replace('-', '')}"
    return rrule


def compute_instance_start(base_start: datetime | None, base_date_key: str, slot_date: str) -> datetime | None:
    """base 의 start_time 을 슬롯 날짜로 평행이동해 반환 (시각 유지, 날짜만 변경)."""
    if base_start is None:
        return None
    base_d = date.fromisoformat(base_date_key)
    slot_d = date.fromisoformat(slot_date)
    offset = slot_d - base_d
    return base_start + timedelta(days=offset.days)


def compute_instance_end(base_end: datetime | None, base_date_key: str, slot_date: str) -> datetime | None:
    """base 의 end_time 을 슬롯 날짜로 평행이동해 반환."""
    if base_end is None:
        return None
    base_d = date.fromisoformat(base_date_key)
    slot_d = date.fromisoformat(slot_date)
    offset = slot_d - base_d
    return base_end + timedelta(days=offset.days)


def make_virtual(base: "Todo", slot_date: str) -> "Todo":
    """base + slot_date 로 가상 인스턴스(DB 미저장) 생성.

    id 는 "{base.id}::{slot_date}" 합성 — DB row 없이 라우팅 가능.
    """
    from app.todo.domain.models.todo import Todo  # 순환 임포트 방지

    inst_start = compute_instance_start(base.start_time, base.date_key, slot_date)
    inst_end = compute_instance_end(base.end_time, base.date_key, slot_date)
    now = datetime.now(timezone.utc)
    return Todo(
        id=f"{base.id}::{slot_date}",
        user_id=base.user_id,
        title=base.title,
        status=base.status,
        date_key=slot_date,
        description=base.description,
        start_time=inst_start,
        end_time=inst_end,
        timezone=base.timezone,
        created_at=base.created_at,
        updated_at=base.updated_at,
        completed_at=base.completed_at,
        # 반복 메타
        recurrence_rule=None,
        series_rule=base.recurrence_rule,
        series_id=base.id,
        original_date_key=slot_date,
        original_start_time=inst_start,
        master_google_event_id=base.google_event_id,
        tags=list(base.tags),
        # GCal push — 가상 인스턴스는 base 와 동일한 push 상태를 노출하지 않는다
        calendar_push_status=None,
        google_event_id=None,
        push_intent=None,
        push_started_at=None,
        sync_attempt_id=None,
        push_retry_count=0,
    )


def build_gcal_instance_id(
    base_google_event_id: str,
    original_start_time_utc: datetime | None,
    slot_date: str | None = None,
) -> str:
    """GCal instance ID: "{base_event_id}_{originalStartTime in UTC compact format}".

    시간 이벤트: "YYYYMMDDTHHmmssZ" 포맷 (original_start_time_utc 사용).
    all-day 이벤트: "YYYYMMDD" 포맷 (slot_date 사용).
    """
    if original_start_time_utc is not None:
        ts = original_start_time_utc.astimezone(timezone.utc)
        compact = ts.strftime("%Y%m%dT%H%M%SZ")
    elif slot_date is not None:
        compact = slot_date.replace("-", "")
    else:
        raise ValueError("Either original_start_time_utc or slot_date must be provided")
    return f"{base_google_event_id}_{compact}"


def is_virtual_id(todo_id: str) -> bool:
    """"::" 를 포함하는 합성 ID 인지 확인 — 라우터/유스케이스에서 분기 판단."""
    return "::" in todo_id


def parse_virtual_id(todo_id: str) -> tuple[str, str]:
    """"{base_id}::{slot_date}" → (base_id, slot_date)."""
    base_id, slot_date = todo_id.split("::", 1)
    return base_id, slot_date
