from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse
from app.shared.presentation.validators import parse_date_range
from app.todo.application.dtos.commands import UNSET, CreateTodoCommand, UpdateTodoCommand
from app.todo.application.dtos.queries import GetTodosByDateQuery, GetTodosByRangeQuery, GetTodoStatsQuery
from app.todo.application.use_cases.add_calendar_link import AddCalendarLinkUseCase
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.get_todo_stats import GetTodoStatsUseCase
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.application.use_cases.remove_calendar_link import RemoveCalendarLinkUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.google_calendar.application.use_cases.get_calendar_events import (
    GetCalendarEventsUseCase,
)
from app.todo.presentation.requests.requests import TodoCreateRequest, TodoUpdateRequest
from app.todo.presentation.responses.responses import TodoResponse, TodoStatsResponse
from app.user.domain.repositories.repository import IUserRepository

router = APIRouter(prefix="/todos", tags=["todos"], route_class=DishkaRoute)

_MAX_TODO_RANGE_DAYS = 366  # 일 년


def _enqueue_push(user_id: str, todo_id: str) -> None:
    """즉시 단건 push task enqueue (calendar 큐). 미연결/미대상이면 워커가 no-op."""
    from app.worker.tasks.push_calendars import push_calendar_event_task

    push_calendar_event_task.apply_async(args=[user_id, todo_id], queue="calendar")


def _enqueue_delete(user_id: str, google_event_id: str) -> None:
    """best-effort Google 이벤트 삭제 task enqueue (전체 todo 삭제 시)."""
    from app.worker.tasks.push_calendars import delete_calendar_event_task

    delete_calendar_event_task.apply_async(
        args=[user_id, google_event_id], queue="calendar"
    )


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[TodoResponse]],
)
async def get_todos(
    by_date_uc: FromDishka[GetTodosByDateUseCase],
    by_range_uc: FromDishka[GetTodosByRangeUseCase],
    calendar_uc: FromDishka[GetCalendarEventsUseCase],
    current_user: UserContext = Depends(get_current_user),
    date_key: str | None = Query(default=None, alias="dateKey"),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> ApiResponse[list[TodoResponse]]:
    # Google Calendar 원본 이벤트도 pull-sync 시 todo 로 승격되므로(SyncCalendarEventsUseCase),
    # 더 이상 별도 events 리스트를 반환하지 않는다 — todos 하나로 통합.
    # calendar_uc 호출(온디맨드 sync 트리거 + last_active_at 갱신)은 todo 조회보다
    # 먼저 실행해야, 이번 요청에서 새로 승격된 이벤트도 todos 응답에 바로 반영된다.
    if date_key:
        await calendar_uc.execute(current_user.id, date_key, date_key)
        todos = await by_date_uc.execute(
            GetTodosByDateQuery(user_id=current_user.id, date_key=date_key)
        )
    elif from_date and to_date:
        parse_date_range(from_date, to_date, _MAX_TODO_RANGE_DAYS)
        await calendar_uc.execute(current_user.id, from_date, to_date)
        todos = await by_range_uc.execute(
            GetTodosByRangeQuery(user_id=current_user.id, from_date=from_date, to_date=to_date)
        )
    else:
        todos = []
    return ApiResponse.ok([TodoResponse.from_entity(t) for t in todos])


@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TodoStatsResponse],
)
async def get_todo_stats(
    use_case: FromDishka[GetTodoStatsUseCase],
    user_repo: FromDishka[IUserRepository],
    current_user: UserContext = Depends(get_current_user),
    range: str = Query(default="today", pattern="^(today|week|month)$"),
    tz: str | None = Query(default=None),
) -> ApiResponse[TodoStatsResponse]:
    if tz is None:
        user = await user_repo.find_by_id(current_user.id)
        tz = user.timezone if user else "UTC"
    result = await use_case.execute(
        GetTodoStatsQuery(user_id=current_user.id, range=range, tz=tz)
    )
    return ApiResponse.ok(result)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TodoResponse],
)
async def create_todo(
    body: TodoCreateRequest,
    use_case: FromDishka[CreateTodoUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TodoResponse]:
    todo = await use_case.execute(
        CreateTodoCommand(
            user_id=current_user.id,
            title=body.title,
            date_key=body.date_key,
            description=body.description,
            status=body.status,
            start_time=body.start_time,
            end_time=body.end_time,
            timezone=body.timezone,
            push_to_calendar=body.push_to_calendar,
            recurrence_rule=body.recurrence_rule.to_domain() if body.recurrence_rule else None,
            tags=body.tags,
        )
    )
    if todo.calendar_push_status in ("pending", "pending_delete"):
        _enqueue_push(current_user.id, todo.id)
    return ApiResponse.created(TodoResponse.from_entity(todo))


@router.patch(
    "/{todo_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TodoResponse],
)
async def update_todo(
    todo_id: str,
    body: TodoUpdateRequest,
    use_case: FromDishka[UpdateTodoUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TodoResponse]:
    provided = body.model_fields_set
    todo = await use_case.execute(
        UpdateTodoCommand(
            id=todo_id,
            user_id=current_user.id,
            title=body.title,
            status=body.status,
            description=body.description,
            date_key=body.date_key,
            start_time=body.start_time if "start_time" in provided else UNSET,
            end_time=body.end_time if "end_time" in provided else UNSET,
            timezone=body.timezone if "timezone" in provided else UNSET,
            recurrence_scope=body.recurrence_scope,
            recurrence_rule=body.recurrence_rule.to_domain() if body.recurrence_rule else None,
            tags=(body.tags or []) if "tags" in provided else UNSET,
        )
    )
    if todo.calendar_push_status in ("pending", "pending_delete"):
        _enqueue_push(current_user.id, todo.id)
    return ApiResponse.ok(TodoResponse.from_entity(todo))


@router.delete(
    "/{todo_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def delete_todo(
    todo_id: str,
    use_case: FromDishka[DeleteTodoUseCase],
    current_user: UserContext = Depends(get_current_user),
    recurrence_scope: str = Query(default="this", alias="recurrenceScope"),
) -> ApiResponse[None]:
    google_event_id = await use_case.execute(
        todo_id=todo_id, user_id=current_user.id, recurrence_scope=recurrence_scope
    )
    if google_event_id:
        _enqueue_delete(current_user.id, google_event_id)
    return ApiResponse.ok(None)


@router.post(
    "/{todo_id}/calendar-link",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def add_calendar_link(
    todo_id: str,
    use_case: FromDishka[AddCalendarLinkUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    """기존 todo 를 Google Calendar 에 연동(사이드바 '캘린더에 추가')."""
    await use_case.execute(todo_id=todo_id, user_id=current_user.id)
    _enqueue_push(current_user.id, todo_id)
    return ApiResponse.ok(None)


@router.delete(
    "/{todo_id}/calendar-link",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def remove_calendar_link(
    todo_id: str,
    use_case: FromDishka[RemoveCalendarLinkUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    """todo 는 유지한 채 Google Calendar 연동만 해제(사이드바 '캘린더에서 빼기')."""
    enqueued = await use_case.execute(todo_id=todo_id, user_id=current_user.id)
    if enqueued:
        _enqueue_push(current_user.id, todo_id)
    return ApiResponse.ok(None)
