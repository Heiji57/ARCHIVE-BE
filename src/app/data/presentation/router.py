"""휴지통 API(12 §1). 할 일·회고 모듈의 휴지통을 모아 보여 준다."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query

from app.data.application.use_cases.trash import TrashUseCase
from app.data.presentation.responses.responses import TrashItemResponse, TrashListResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse
from app.todo.infrastructure.side_effects import enqueue_push
from app.topic.domain.repositories.repository import IEmbeddingQueueRepository

router = APIRouter(prefix="/trash", tags=["data"], route_class=DishkaRoute)


@router.get("", response_model=ApiResponse[TrashListResponse])
async def list_trash(
    use_case: FromDishka[TrashUseCase],
    current_user: UserContext = Depends(get_current_user),
    kind: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[TrashListResponse]:
    items, total = await use_case.list(current_user.id, kind, page, size)
    return ApiResponse.ok(
        TrashListResponse(
            items=[TrashItemResponse.from_entity(i) for i in items],
            total=total,
            page=page,
            size=size,
        )
    )


@router.post("/{kind}/{item_id}/restore", response_model=ApiResponse[None])
async def restore_trash_item(
    kind: str,
    item_id: str,
    use_case: FromDishka[TrashUseCase],
    queue_repo: FromDishka[IEmbeddingQueueRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    outcome = await use_case.restore(current_user.id, kind, item_id)
    if outcome.reembed_todo_id:
        await queue_repo.enqueue("todo", outcome.reembed_todo_id, current_user.id)
    if outcome.push_todo_id:
        enqueue_push(current_user.id, outcome.push_todo_id)
    return ApiResponse.ok(None)


@router.delete("/{kind}/{item_id}", response_model=ApiResponse[None])
async def purge_trash_item(
    kind: str,
    item_id: str,
    use_case: FromDishka[TrashUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.purge(current_user.id, kind, item_id)
    return ApiResponse.ok(None)


@router.delete("", response_model=ApiResponse[None])
async def empty_trash(
    use_case: FromDishka[TrashUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.empty(current_user.id)
    return ApiResponse.ok(None)
