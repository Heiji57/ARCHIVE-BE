"""반복 Todo 관련 순수 도메인 유틸리티.

- generate_slots_from: base event 의 RecurrenceRule 로부터 슬롯 날짜(YYYY-MM-DD) 시퀀스 생성.
- make_virtual: 슬롯 날짜 + base 로부터 가상 Todo 인스턴스 생성.
- build_gcal_instance_id: GCal instance ID 계산 (base_event_id + originalStartTime UTC).
- compute_instance_start/end: 슬롯에 맞게 base 의 start/end_time 을 보정.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.shared.domain.utils.id import generate_id

if TYPE_CHECKING:
    from app.todo.domain.models.todo import RecurrenceRule, Todo


def generate_slots_from(
    rule: "RecurrenceRule",
    series_start: str,   # base.date_key
    range_start: str,    # 조회 범위 시작 (포함)
    range_end: str,      # 조회 범위 끝 (포함)
) -> list[str]:
    """series_start 에서 delta 씩 증가해 [range_start, range_end] 에 속하는 슬롯 반환."""
    if rule.unit == "day":
        delta = timedelta(days=rule.interval)
    else:
        delta = timedelta(weeks=rule.interval)

    effective_end = range_end
    if rule.until and rule.until < range_end:
        effective_end = rule.until

    # series_start 부터 delta 씩 증가해 range_start 이상인 첫 슬롯을 찾는다.
    s_date = date.fromisoformat(series_start)
    r_start = date.fromisoformat(range_start)
    r_end = date.fromisoformat(effective_end)

    if s_date > r_end:
        return []

    # series_start 에서 몇 스텝 지나야 range_start 에 도달하는지 계산
    if s_date < r_start:
        diff = (r_start - s_date).days
        if rule.unit == "day":
            steps = (diff + rule.interval - 1) // rule.interval
        else:
            steps = (diff + rule.interval * 7 - 1) // (rule.interval * 7)
        current = s_date + delta * steps
    else:
        current = s_date

    slots: list[str] = []
    while current <= r_end:
        if current >= r_start:
            slots.append(current.isoformat())
        current += delta
    return slots


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
        series_id=base.id,
        original_date_key=slot_date,
        original_start_time=inst_start,
        master_google_event_id=base.google_event_id,
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
