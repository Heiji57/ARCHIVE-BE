from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.shared.domain.models.base import BaseEntity
from app.todo.domain.exceptions.exceptions import (
    TodoAlreadyCompletedException,
    TodoAlreadyInProgressException,
)
from app.todo.domain.models.value_objects import TaskStatus


@dataclass(frozen=True)
class RecurrenceRule:
    """반복 주기 정의 — base event 에만 저장된다."""
    unit: Literal["day", "week"]
    interval: int  # 1~365
    until: str | None = None  # YYYY-MM-DD (inclusive) or None = indefinite


@dataclass(kw_only=True)
class Todo(BaseEntity):
    user_id: str
    title: str
    status: TaskStatus
    date_key: str  # YYYY-MM-DD
    description: str = ""
    completed_at: datetime | None = None
    start_time: datetime | None = None  # UTC
    end_time: datetime | None = None  # UTC
    timezone: str | None = None  # IANA timezone snapshot at creation
    # ── 반복 Todo 필드 ──────────────────────────────────────────────────────────
    # recurrence_rule non-null + series_id null → base event (순수 설정 템플릿)
    # recurrence_rule null + series_id non-null → exception row (실체화된 인스턴스)
    recurrence_rule: RecurrenceRule | None = None
    series_id: str | None = None          # 시리즈 base todo id
    original_date_key: str | None = None  # 원래 슬롯 날짜 (이동해도 불변 — GCal instance key)
    original_start_time: datetime | None = None  # 슬롯 start_time (UTC, GCal instance ID 계산용)
    master_google_event_id: str | None = None  # base 의 GCal event id 스냅샷 (exception push용)
    tags: list[str] = field(default_factory=list)
    due_date_key: str | None = None  # YYYY-MM-DD (inclusive), must be >= date_key
    # ── Google Calendar push 상태 (읽기 전용 뷰) ────────────────────────────────
    # 이 필드들은 응답 노출 / claim 결과 매핑을 위해 엔티티가 실어 나르지만,
    # 쓰기는 repo 의 타겟 SQL(mark_for_push / claim / heartbeat / finalize / bulk_clear)
    # 로만 수행한다. 콘텐츠 save(merge)는 이 컬럼들을 건드리지 않는다 — 워커 push
    # 진행 상태와의 clobber 방지. (_to_model 에서 제외되어 merge 가 skip)
    calendar_push_status: str | None = None  # None|pending|syncing|synced|failed|pending_delete
    google_event_id: str | None = None
    push_intent: str | None = None  # 'push' | 'delete'
    push_started_at: datetime | None = None
    sync_attempt_id: str | None = None
    push_retry_count: int = 0

    @property
    def is_calendar_linked(self) -> bool:
        """Google Calendar 에 push 되었거나 push 대기/진행 중인지 (연동 상태)."""
        return self.calendar_push_status is not None

    @property
    def is_series_base(self) -> bool:
        """반복 시리즈의 base event 인지 (순수 설정 템플릿, 화면에 직접 노출 안 됨)."""
        return self.recurrence_rule is not None and self.series_id is None

    def complete(self) -> None:
        if self.status == TaskStatus.DONE:
            raise TodoAlreadyCompletedException()
        self.status = TaskStatus.DONE
        self.completed_at = datetime.now(timezone.utc)

    def start(self) -> None:
        if self.status == TaskStatus.IN_PROGRESS:
            raise TodoAlreadyInProgressException()
        self.status = TaskStatus.IN_PROGRESS
        self.completed_at = None

    def move_to(self, date_key: str) -> None:
        """날짜 이동 — 시간이 있는 todo 는 start/end 도 새 날짜로 평행이동한다.

        Google Calendar push 는 시간 이벤트를 start_time/end_time 으로만 만들고
        date_key 는 보지 않는다. date_key 만 바꾸면 캘린더 이벤트가 옛 날짜에 남는다.
        기준은 기존 date_key 가 아니라 start(없으면 end)의 로컬 날짜 — 이미 어긋난
        row 도 이동 시 date_key 와 다시 일치한다. 로컬 벽시계 시각과 start~end 일수
        차이는 유지한다(DST 무관). 같은 요청에 start/end 가 명시되면 호출자가 이후
        덮어쓴다.
        """
        anchor = self.start_time or self.end_time
        if anchor is not None:
            tz = self._zone()
            delta = date.fromisoformat(date_key) - _as_utc(anchor).astimezone(tz).date()
            self.start_time = _shift_local_days(self.start_time, tz, delta)
            self.end_time = _shift_local_days(self.end_time, tz, delta)
        self.date_key = date_key

    def _zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone or "UTC")
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _shift_local_days(dt: datetime | None, tz: ZoneInfo, delta: timedelta) -> datetime | None:
    """로컬 벽시계 기준으로 delta 일 이동 후 UTC 로 반환."""
    if dt is None:
        return None
    return (_as_utc(dt).astimezone(tz) + delta).astimezone(timezone.utc)


@dataclass(frozen=True, kw_only=True)
class TodoMeta:
    """식별·표시에만 필요한 필드를 담는 읽기 모델 — JournalEntryMeta 와 같은 이유.

    `Todo` 는 반복 규칙·캘린더 push 상태·시각 스냅샷까지 스물몇 개 컬럼을 가진다.
    "이 주제에 어떤 할일이 묶이는가" 같은 경로는 그중 다섯 개만 읽는다.
    """

    id: str
    title: str
    date_key: str  # YYYY-MM-DD
    status: TaskStatus
    tags: list[str] = field(default_factory=list)
