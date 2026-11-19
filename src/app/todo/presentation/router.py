from typing import Literal

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.calendars.domain.repositories.repository import ICalendarRepository
from app.google_calendar.application.use_cases.get_calendar_events import (
    GetCalendarEventsUseCase,
)
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse
from app.shared.presentation.validators import parse_date_range
from app.todo.application.dtos.commands import UNSET, CreateTodoCommand, UpdateTodoCommand
from app.todo.application.dtos.queries import (
    GetTodosByDateQuery,
    GetTodosByRangeQuery,
    GetTodosFilteredQuery,
    GetTodoStatsQuery,
    SearchTagsQuery,
)
from app.todo.application.use_cases.add_calendar_link import AddCalendarLinkUseCase
from app.todo.application.use_cases.batch_update_todos import BatchUpdateTodosUseCase
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.get_todo_stats import GetTodoStatsUseCase
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.application.use_cases.get_todos_filtered import GetTodosFilteredUseCase
from app.todo.application.use_cases.manage_tags import (
    DeleteTagUseCase,
    ListTagsUseCase,
    ReorderTagsUseCase,
    UpdateTagCommand,
    UpdateTagUseCase,
)
from app.todo.application.use_cases.remove_calendar_link import RemoveCalendarLinkUseCase
from app.todo.application.use_cases.search_tags import SearchTagsUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.domain.exceptions.exceptions import TodoQueryConflictException
from app.todo.domain.models.todo import Todo
from app.todo.infrastructure.side_effects import after_update as _after_update
from app.todo.infrastructure.side_effects import enqueue_delete as _enqueue_delete
from app.todo.infrastructure.side_effects import enqueue_push as _enqueue_push
from app.todo.presentation.requests.requests import (
    ReorderTagsRequest,
    TodoBatchRequest,
    TodoCreateRequest,
    TodoUpdateRequest,
    UpdateTagRequest,
)
from app.todo.presentation.responses.responses import (
    TagResponse,
    TagSearchResponse,
    TodoBatchResponse,
    TodoResponse,
    TodoStatsResponse,
)
from app.topic.domain.repositories.repository import IEmbeddingQueueRepository, ITodoEmbeddingRepository
from app.user.domain.repositories.repository import IUserRepository

router = APIRouter(prefix="/todos", tags=["todos"], route_class=DishkaRoute)

_MAX_TODO_RANGE_DAYS = 366  # 일 년
_MAX_DUE_RANGE_DAYS = 366


def _to_update_command(todo_id: str, user_id: str, body: TodoUpdateRequest) -> UpdateTodoCommand:
    """PATCH 본문 → 명령. 단건 수정과 묶음 수정이 같은 규칙을 쓴다."""
    provided = body.model_fields_set
    return UpdateTodoCommand(
        id=todo_id,
        user_id=user_id,
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
        due_date_key=body.due_date_key if "due_date_key" in provided else UNSET,
        calendar_id=body.calendar_id if "calendar_id" in provided else UNSET,
    )


async def _calendar_scope(
    calendar_repo: ICalendarRepository, user_id: str, calendar_ids: str | None
) -> tuple[list[str] | None, bool]:
    """`calendarIds` → (캘린더 id 목록, 기본 캘린더(NULL) 포함 여부).

    파라미터가 없으면 (None, False).
    """
    if calendar_ids is None:
        return None, False
    wanted = [c for c in calendar_ids.split(",") if c]
    default = await calendar_repo.find_default(user_id)
    return wanted, default is not None and default.id in wanted


async def _filter_by_calendars(
    calendar_repo: ICalendarRepository,
    user_id: str,
    todos: list[Todo],
    calendar_ids: str | None,
) -> list[Todo]:
    """`calendarIds=a,b` — 그 캘린더들의 할 일만.

    calendar_id 가 NULL 인 할 일은 기본 캘린더 소속이다.
    """
    if calendar_ids is None:
        return todos
    wanted = {c for c in calendar_ids.split(",") if c}
    default = await calendar_repo.find_default(user_id)
    default_id = default.id if default else None
    return [t for t in todos if (t.calendar_id or default_id) in wanted]


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[TodoResponse]],
)
async def get_todos(
    by_date_uc: FromDishka[GetTodosByDateUseCase],
    by_range_uc: FromDishka[GetTodosByRangeUseCase],
    filtered_uc: FromDishka[GetTodosFilteredUseCase],
    calendar_uc: FromDishka[GetCalendarEventsUseCase],
    user_repo: FromDishka[IUserRepository],
    calendar_repo: FromDishka[ICalendarRepository],
    current_user: UserContext = Depends(get_current_user),
    date_key: str | None = Query(default=None, alias="dateKey"),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    overdue: bool = Query(default=False),
    due: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}$"),
    calendar_push_status: Literal["failed"] | None = Query(
        default=None, alias="calendarPushStatus"
    ),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    calendar_ids: str | None = Query(default=None, alias="calendarIds"),
) -> ApiResponse[list[TodoResponse]]:
    modes = [
        bool(date_key or from_date or to_date),
        overdue,
        due is not None,
        calendar_push_status is not None,
    ]
    if sum(modes) > 1:
        raise TodoQueryConflictException(
            "Use only one of dateKey/from/to, overdue, due, calendarPushStatus."
        )
    if overdue or due is not None or calendar_push_status is not None:
        # 보이는 기간과 무관한 조회 — 온디맨드 캘린더 sync 는 기간 조회에서만 한다.
        due_from = due_to = None
        if due is not None:
            due_from, due_to = due.split("..")
            parse_date_range(due_from, due_to, _MAX_DUE_RANGE_DAYS)
            if due_from > due_to:
                raise HTTPException(status_code=422, detail="due 의 시작일이 종료일보다 늦습니다.")
        user = await user_repo.find_by_id(current_user.id)
        # 페이지로 나눠 받는 모드라 캘린더 거르기도 SQL 에서 한다(메모리에서 거르면 페이지가 빈다).
        cal_ids, include_default = await _calendar_scope(
            calendar_repo, current_user.id, calendar_ids
        )
        todos = await filtered_uc.execute(
            GetTodosFilteredQuery(
                user_id=current_user.id,
                tz=user.timezone if user else "UTC",
                overdue=overdue,
                due_from=due_from,
                due_to=due_to,
                push_status=calendar_push_status,
                calendar_ids=cal_ids,
                include_default_calendar=include_default,
                page=page,
                size=size,
            )
        )
        return ApiResponse.ok([TodoResponse.from_entity(t) for t in todos])
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
    todos = await _filter_by_calendars(calendar_repo, current_user.id, todos, calendar_ids)
    return ApiResponse.ok([TodoResponse.from_entity(t) for t in todos])


@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TodoStatsResponse],
)
async def get_todo_stats(
    use_case: FromDishka[GetTodoStatsUseCase],
    user_repo: FromDishka[IUserRepository],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
    range: str = Query(default="today", pattern="^(today|week|month|all)$"),
    tz: str | None = Query(default=None),
) -> ApiResponse[TodoStatsResponse]:
    if tz is None:
        user = await user_repo.find_by_id(current_user.id)
        tz = user.timezone if user else "UTC"
    settings = await settings_repo.find_by_user_id(current_user.id)
    result = await use_case.execute(
        GetTodoStatsQuery(
            user_id=current_user.id,
            range=range,
            tz=tz,
            week_start=settings.week_start if settings else "mon",
        )
    )
    return ApiResponse.ok(result)


@router.get(
    "/tags/search",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TagSearchResponse],
)
async def search_tags(
    use_case: FromDishka[SearchTagsUseCase],
    current_user: UserContext = Depends(get_current_user),
    q: str = Query(..., min_length=1, max_length=20),
    limit: int = Query(default=8, ge=1, le=20),
) -> ApiResponse[TagSearchResponse]:
    tags = await use_case.execute(
        SearchTagsQuery(user_id=current_user.id, query=q, limit=limit)
    )
    return ApiResponse.ok(TagSearchResponse(tags=tags))


@router.get(
    "/tags",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[TagResponse]],
)
async def list_tags(
    use_case: FromDishka[ListTagsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[TagResponse]]:
    """사용 중인 태그 전체 — 이름, 붙은 할 일 수, 색(c1~c8 또는 null), 순서."""
    tags = await use_case.execute(current_user.id)
    return ApiResponse.ok([TagResponse.from_domain(t) for t in tags])


@router.put(
    "/tags/order",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[TagResponse]],
)
async def reorder_tags(
    body: ReorderTagsRequest,
    use_case: FromDishka[ReorderTagsUseCase],
    list_uc: FromDishka[ListTagsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[TagResponse]]:
    await use_case.execute(current_user.id, body.names)
    tags = await list_uc.execute(current_user.id)
    return ApiResponse.ok([TagResponse.from_domain(t) for t in tags])


@router.patch(
    "/tags/{name}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TagResponse],
)
async def update_tag(
    name: str,
    body: UpdateTagRequest,
    use_case: FromDishka[UpdateTagUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TagResponse]:
    """이름(이미 있는 이름이면 합침)·색·순서. 이름을 바꾸면 모든 할 일의 태그가 함께 바뀐다."""
    provided = body.model_fields_set
    tag = await use_case.execute(
        UpdateTagCommand(
            user_id=current_user.id,
            name=name,
            new_name=body.name if "name" in provided and body.name else UNSET,
            color=body.color if "color" in provided else UNSET,
            sort_order=body.sort_order if "sort_order" in provided else UNSET,
        )
    )
    return ApiResponse.ok(TagResponse.from_domain(tag))


@router.delete(
    "/tags/{name}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def delete_tag(
    name: str,
    use_case: FromDishka[DeleteTagUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    """모든 할 일에서 그 태그를 뺀다(할 일은 남는다)."""
    await use_case.execute(current_user.id, name)
    return ApiResponse.ok(None)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TodoResponse],
)
async def create_todo(
    body: TodoCreateRequest,
    use_case: FromDishka[CreateTodoUseCase],
    queue_repo: FromDishka[IEmbeddingQueueRepository],
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
            due_date_key=body.due_date_key,
            calendar_id=body.calendar_id,
        )
    )
    if todo.calendar_push_status in ("pending", "pending_delete"):
        _enqueue_push(current_user.id, todo.id)
    if not todo.is_series_base:
        await queue_repo.enqueue("todo", todo.id, current_user.id)
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
    queue_repo: FromDishka[IEmbeddingQueueRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TodoResponse]:
    outcome = await use_case.execute(_to_update_command(todo_id, current_user.id, body))
    await _after_update(queue_repo, current_user.id, outcome.todo, outcome.extra_push_todo_id)
    return ApiResponse.ok(TodoResponse.from_entity(outcome.todo))


@router.post(
    "/batch",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TodoBatchResponse],
)
async def batch_update_todos(
    body: TodoBatchRequest,
    use_case: FromDishka[BatchUpdateTodosUseCase],
    queue_repo: FromDishka[IEmbeddingQueueRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TodoBatchResponse]:
    """여러 todo 를 한 번에 수정 (전부 아니면 전무). 하나라도 실패하면 400 TODO_BATCH_FAILED."""
    result = await use_case.execute(
        current_user.id,
        [_to_update_command(op.id, current_user.id, op.patch) for op in body.operations],
    )
    for outcome in result.outcomes:
        await _after_update(queue_repo, current_user.id, outcome.todo, outcome.extra_push_todo_id)
    return ApiResponse.ok(
        TodoBatchResponse(
            todos=[TodoResponse.from_entity(o.todo) for o in result.outcomes],
            previous=[TodoResponse.from_entity(t) for t in result.previous],
        )
    )


@router.delete(
    "/{todo_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def delete_todo(
    todo_id: str,
    use_case: FromDishka[DeleteTodoUseCase],
    todo_emb_repo: FromDishka[ITodoEmbeddingRepository],
    current_user: UserContext = Depends(get_current_user),
    recurrence_scope: str = Query(default="this", alias="recurrenceScope"),
) -> ApiResponse[None]:
    outcome = await use_case.execute(
        todo_id=todo_id, user_id=current_user.id, recurrence_scope=recurrence_scope
    )
    if outcome.delete_google_event_id:
        _enqueue_delete(current_user.id, outcome.delete_google_event_id)
    if outcome.push_todo_id:
        _enqueue_push(current_user.id, outcome.push_todo_id)
    await todo_emb_repo.delete_by_todo(todo_id)
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
