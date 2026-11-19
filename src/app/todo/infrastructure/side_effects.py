"""할 일 수정 뒤 후속 작업 — Google Calendar push 예약과 임베딩 갱신 표시.

할 일을 바꾸는 모든 경로(할 일 라우터, AI 제안 적용)가 같은 후속 작업을 하도록 한곳에 둔다.
"""

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
) -> None:
    """수정 뒤 후속 작업 — Google Calendar push 예약, 임베딩 갱신 표시."""
    if todo.calendar_push_status in ("pending", "pending_delete"):
        enqueue_push(user_id, todo.id)
    if extra_push_todo_id:
        enqueue_push(user_id, extra_push_todo_id)
    if not todo.is_series_base:
        await queue_repo.enqueue("todo", todo.id, user_id)
