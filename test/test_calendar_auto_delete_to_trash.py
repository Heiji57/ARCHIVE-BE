"""08 §1 — Google 에서 지운 일정의 할 일은 휴지통으로, 동기화 한 번에 알림 하나."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.google_calendar.application.use_cases.sync_calendar_events import (
    SyncCalendarEventsUseCase,
)
from app.google_calendar.domain.models.calendar_connection import GoogleCalendarConnection
from app.google_calendar.infrastructure.api.google_calendar_client import (
    CalendarEventsPage,
    RawCalendarEvent,
)
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus

_NOW = datetime.now(UTC)


def _cancelled(gid: str) -> RawCalendarEvent:
    return RawCalendarEvent(
        google_event_id=gid,
        calendar_id="primary",
        title="",
        description=None,
        location=None,
        start_at=None,
        end_at=None,
        all_day=False,
        date_key="2026-11-16",
        timezone=None,
        status="cancelled",
        html_link=None,
    )


class _Conn:
    def __init__(self) -> None:
        self.conn = GoogleCalendarConnection(
            id="gcc_1",
            user_id="u",
            google_user_id="g",
            access_token="tok",
            refresh_token="r",
            token_expires_at=_NOW + timedelta(hours=1),
            scope="s",
            created_at=_NOW,
        )

    async def find_by_user_id(self, user_id):
        return self.conn

    async def save(self, conn):
        return conn


class _Events:
    async def delete_by_google_ids(self, user_id, ids):
        pass


class _Api:
    async def list_events(self, *a, **kw):
        return CalendarEventsPage([_cancelled("g1"), _cancelled("g2")], "next")


class _Todos:
    def __init__(self) -> None:
        self.trashed: list[tuple[str, bool]] = []

    async def find_by_google_event_ids(self, user_id, ids):
        return [
            Todo(
                id=f"todo_{g}",
                user_id=user_id,
                title="t",
                status=TaskStatus.NOT_START,
                date_key="2026-11-16",
                created_at=_NOW,
                google_event_id=g,
            )
            for g in ids
        ]

    async def soft_delete(self, id, user_id, *, with_series=False):
        self.trashed.append((id, with_series))


class _Settings:
    async def find_by_user_id(self, user_id):
        return SimpleNamespace(calendar_auto_delete_todo=True)


class _Notice:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def todos_trashed(self, user_id, count):
        self.calls.append(count)


async def test_cancelled_events_trash_todos_with_one_notification():
    todos, notice = _Todos(), _Notice()
    config = SimpleNamespace(
        calendar_sync_staleness_seconds=0,
        calendar_initial_window_days=30,
        calendar_future_window_days=30,
    )
    uc = SyncCalendarEventsUseCase(
        _Conn(),
        _Events(),
        _Api(),
        config,
        todos,
        _Settings(),
        notice,  # type: ignore[arg-type]
    )
    await uc.execute("u", force=True)
    assert todos.trashed == [("todo_g1", False), ("todo_g2", False)]
    assert notice.calls == [2]
