from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse
from app.todo.application.dtos.commands import CreateTodoCommand, UpdateTodoCommand
from app.todo.application.dtos.queries import GetTodosByDateQuery, GetTodosByRangeQuery
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.presentation.requests.requests import TodoCreateRequest, TodoUpdateRequest
from app.todo.presentation.responses.responses import TodoResponse

router = APIRouter(prefix="/todos", tags=["todos"], route_class=DishkaRoute)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[TodoResponse]],
)
async def get_todos(
    by_date_uc: FromDishka[GetTodosByDateUseCase],
    by_range_uc: FromDishka[GetTodosByRangeUseCase],
    current_user: UserContext = Depends(get_current_user),
    date_key: str | None = Query(default=None, alias="dateKey"),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> ApiResponse[list[TodoResponse]]:
    if date_key:
        todos = await by_date_uc.execute(
            GetTodosByDateQuery(user_id=current_user.id, date_key=date_key)
        )
    elif from_date and to_date:
        todos = await by_range_uc.execute(
            GetTodosByRangeQuery(user_id=current_user.id, from_date=from_date, to_date=to_date)
        )
    else:
        todos = []
    return ApiResponse.ok([TodoResponse.from_entity(t) for t in todos])


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
        )
    )
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
    todo = await use_case.execute(
        UpdateTodoCommand(
            id=todo_id,
            user_id=current_user.id,
            title=body.title,
            status=body.status,
            description=body.description,
            date_key=body.date_key,
        )
    )
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
) -> ApiResponse[None]:
    await use_case.execute(todo_id=todo_id, user_id=current_user.id)
    return ApiResponse.ok(None)
