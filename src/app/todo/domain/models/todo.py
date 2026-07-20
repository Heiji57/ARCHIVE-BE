from dataclasses import dataclass
from datetime import datetime, timezone

from app.shared.domain.models.base import BaseEntity
from app.todo.domain.exceptions.exceptions import (
    TodoAlreadyCompletedException,
    TodoAlreadyInProgressException,
)
from app.todo.domain.models.value_objects import TaskStatus


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

    def complete(self) -> None:
        if self.status == TaskStatus.DONE:
            raise TodoAlreadyCompletedException()
        self.status = TaskStatus.DONE
        self.completed_at = datetime.now(timezone.utc)

    def start(self) -> None:
        if self.status == TaskStatus.DONE:
            raise TodoAlreadyCompletedException()
        if self.status == TaskStatus.IN_PROGRESS:
            raise TodoAlreadyInProgressException()
        self.status = TaskStatus.IN_PROGRESS

    def move_to(self, date_key: str) -> None:
        self.date_key = date_key
