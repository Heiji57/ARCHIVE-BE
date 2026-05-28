from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.retrospective.application.dtos.commands import CreateEntryCommand, UpsertEntryCommand
from app.retrospective.application.dtos.queries import GetEntriesQuery
from app.retrospective.application.use_cases.create_entry import CreateEntryUseCase
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.application.use_cases.get_entries import GetEntriesUseCase
from app.retrospective.application.use_cases.get_entry import GetEntryUseCase
from app.retrospective.application.use_cases.upsert_entry import UpsertEntryUseCase
from app.retrospective.presentation.requests.requests import EntryCreateRequest, EntryUpsertRequest
from app.retrospective.presentation.responses.responses import EntryResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/entries", tags=["entries"], route_class=DishkaRoute)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[EntryResponse]],
)
async def get_entries(
    use_case: FromDishka[GetEntriesUseCase],
    current_user: UserContext = Depends(get_current_user),
    retro_type: str | None = Query(default=None, alias="retroType"),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> ApiResponse[list[EntryResponse]]:
    entries = await use_case.execute(
        GetEntriesQuery(
            user_id=current_user.id,
            retro_type=retro_type,
            from_date=from_date,
            to_date=to_date,
        )
    )
    return ApiResponse.ok([EntryResponse.from_entity(e) for e in entries])


@router.get(
    "/{entry_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[EntryResponse],
)
async def get_entry(
    entry_id: str,
    use_case: FromDishka[GetEntryUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[EntryResponse]:
    entry = await use_case.execute(entry_id=entry_id, user_id=current_user.id)
    return ApiResponse.ok(EntryResponse.from_entity(entry))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[EntryResponse],
)
async def create_entry(
    body: EntryCreateRequest,
    use_case: FromDishka[CreateEntryUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[EntryResponse]:
    entry = await use_case.execute(
        CreateEntryCommand(
            user_id=current_user.id,
            date_key=body.date_key,
            title=body.title,
            content=body.content,
            retro_type=body.retro_type,
        )
    )
    return ApiResponse.created(EntryResponse.from_entity(entry))


@router.put(
    "/{entry_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[EntryResponse],
)
async def upsert_entry(
    entry_id: str,
    body: EntryUpsertRequest,
    use_case: FromDishka[UpsertEntryUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[EntryResponse]:
    entry = await use_case.execute(
        UpsertEntryCommand(
            entry_id=entry_id,
            user_id=current_user.id,
            date_key=body.date_key,
            title=body.title,
            content=body.content,
            retro_type=body.retro_type,
        )
    )
    return ApiResponse.ok(EntryResponse.from_entity(entry))


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def delete_entry(
    entry_id: str,
    use_case: FromDishka[DeleteEntryUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(entry_id=entry_id, user_id=current_user.id)
    return ApiResponse.ok(None)
