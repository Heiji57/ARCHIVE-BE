from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.github.domain.models.retrospective_push import RetrospectivePush
from app.github.domain.repositories.retrospective_push_repository import (
    IRetrospectivePushRepository,
)
from app.github.domain.utils.period_mapping import entry_to_period
from app.retrospective.application.dtos.commands import CreateEntryCommand, UpsertEntryCommand
from app.retrospective.application.dtos.queries import GetEntriesQuery
from app.retrospective.application.use_cases.create_entry import CreateEntryUseCase
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.application.use_cases.get_entries import GetEntriesUseCase
from app.retrospective.application.use_cases.get_entry import GetEntryUseCase
from app.retrospective.application.use_cases.upsert_entry import UpsertEntryUseCase
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.presentation.requests.requests import EntryCreateRequest, EntryUpsertRequest
from app.retrospective.presentation.responses.responses import EntryResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/entries", tags=["entries"], route_class=DishkaRoute)


async def _push_map_for_entries(
    push_repo: IRetrospectivePushRepository,
    user_id: str,
    entries: list[JournalEntry],
) -> dict[tuple[str, str], RetrospectivePush]:
    """entry 목록 → (period_type, period_key) → RetrospectivePush 매핑."""
    keys = [entry_to_period(e) for e in entries]
    pushes = await push_repo.find_many(user_id, keys)
    return {(p.period_type, p.period_key): p for p in pushes}


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[EntryResponse]],
)
async def get_entries(
    use_case: FromDishka[GetEntriesUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
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
    push_map = await _push_map_for_entries(push_repo, current_user.id, entries)
    return ApiResponse.ok([
        EntryResponse.from_entity(e, push_map.get(entry_to_period(e)))
        for e in entries
    ])


@router.get(
    "/{entry_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[EntryResponse],
)
async def get_entry(
    entry_id: str,
    use_case: FromDishka[GetEntryUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[EntryResponse]:
    entry = await use_case.execute(entry_id=entry_id, user_id=current_user.id)
    period_type, period_key = entry_to_period(entry)
    push = await push_repo.find_by_period(current_user.id, period_type, period_key)
    return ApiResponse.ok(EntryResponse.from_entity(entry, push))


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
