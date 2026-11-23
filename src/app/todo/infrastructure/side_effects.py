"""할 일 수정 뒤 후속 작업 — Google Calendar push 예약과 임베딩 갱신 표시.

할 일을 바꾸는 모든 경로(할 일 라우터, AI 제안 적용)가 같은 후속 작업을 하도록 한곳에 둔다.
"""

from app.todo.application.ports import TodoChangeObserver
from app.todo.domain.models.todo import Todo
from app.topic.domain.repositories.repository import IEmbeddingQueueRepository


def enqueue_push(user_id: str, todo_id: str) -> None:
    """즉시 단건 push task enqueue (calendar 큐). 미연결/미대상이면 워커가 no-op."""
    from app.worker.tasks.push_calendars import push_calendar_event_task

    push_calendar_event_task.apply_async(args=[user_id, todo_id], queue="calendar")


def enqueue_delete(user_id: str, google_event_id: str) -> None:
    """best-effort Google 이벤트 삭제 task enqueue (전체 todo 삭제 시)."""
    from app.worker.tasks.push_calendars import delete_calendar_event_task

    delete_calendar_event_task.apply_async(args=[user_id, google_event_id], queue="calendar")


async def after_update(
    queue_repo: IEmbeddingQueueRepository,
    user_id: str,
    todo: Todo,
    extra_push_todo_id: str | None,
    *,
    before: Todo | None = None,
    observer: TodoChangeObserver | None = None,
    source: str | None = None,
) -> None:
    """수정 뒤 후속 작업 — Google Calendar push 예약, 임베딩 갱신 표시, 변경 알림(행동 학습).

    `before` 는 한 할 일(한 회차)을 고쳤을 때만 있다 — 시리즈 전체 수정은 알리지 않는다.
    `source` 는 다른 모듈이 대신 고쳤을 때의 출처(AI 추천·제안 적용) — 관찰자에게 그대로 넘긴다.
    """
    if todo.calendar_push_status in ("pending", "pending_delete"):
        enqueue_push(user_id, todo.id)
    if extra_push_todo_id:
        enqueue_push(user_id, extra_push_todo_id)
    if not todo.is_series_base:
        await queue_repo.enqueue("todo", todo.id, user_id)
    if before is not None and observer is not None:
        await observer.changed(user_id, before, todo, source)
