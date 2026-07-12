from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.domain.models.retrospective_push import RetrospectivePush
from app.github.domain.repositories.retrospective_push_repository import (
    IRetrospectivePushRepository,
)
from app.github.domain.utils.period_mapping import entry_to_period, summary_to_period
from app.retrospective.application.dtos.commands import CreateEntryCommand, UpsertEntryCommand
from app.retrospective.application.dtos.queries import GetEntriesPageQuery, GetEntriesQuery
from app.retrospective.application.use_cases.create_entry import CreateEntryUseCase
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.application.use_cases.get_entries import GetEntriesUseCase
from app.retrospective.application.use_cases.get_entries_page import GetEntriesPageUseCase
from app.retrospective.application.use_cases.get_entry import GetEntryUseCase
from app.retrospective.application.use_cases.upsert_entry import UpsertEntryUseCase
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.presentation.requests.requests import EntryCreateRequest, EntryUpsertRequest
from app.retrospective.presentation.responses.responses import (
    EntryPageResponse,
    EntryResponse,
    EntryWithGithubResponse,
)
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse
from app.shared.presentation.validators import parse_date_range

router = APIRouter(prefix="/entries", tags=["entries"], route_class=DishkaRoute)

_MAX_ENTRY_RANGE_DAYS = 366  # 일 년
_MAX_ENTRY_PAGE_SIZE = 50
_VALID_RETRO_TYPES = {t.value for t in RetroType}


async def _is_github_connected(
    oauth_repo: IOAuthConnectionRepository,
    user_id: str,
) -> bool:
    connections = await oauth_repo.find_by_user_id(user_id)
    conn = next((c for c in connections if c.provider == OAuthProvider.GITHUB), None)
    return conn is not None and bool(conn.access_token)


async def _push_map_for_entries(
    push_repo: IRetrospectivePushRepository,
    user_id: str,
    entries: list[JournalEntry],
) -> dict[tuple[str, str], RetrospectivePush]:
    keys = [entry_to_period(e) for e in entries]
    pushes = await push_repo.find_many(user_id, keys)
    return {(p.period_type, p.period_key): p for p in pushes}


async def _push_map_for_summaries(
    push_repo: IRetrospectivePushRepository,
    user_id: str,
    summaries: list[RetroSummary],
) -> dict[tuple[str, str], RetrospectivePush]:
    keys = [summary_to_period(s) for s in summaries]
    pushes = await push_repo.find_many(user_id, keys)
    return {(p.period_type, p.period_key): p for p in pushes}


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[EntryWithGithubResponse]],
)
async def get_entries(
    use_case: FromDishka[GetEntriesUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
    oauth_repo: FromDishka[IOAuthConnectionRepository],
    current_user: UserContext = Depends(get_current_user),
    retro_type: str | None = Query(default=None, alias="retroType"),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> ApiResponse[list[EntryWithGithubResponse]]:
    parse_date_range(from_date, to_date, _MAX_ENTRY_RANGE_DAYS)

    entries = await use_case.execute(
        GetEntriesQuery(
            user_id=current_user.id,
            retro_type=retro_type,
            from_date=from_date,
            to_date=to_date,
        )
    )

    if current_user.is_developer() and await _is_github_connected(oauth_repo, current_user.id):
        push_map = await _push_map_for_entries(push_repo, current_user.id, entries)
        return ApiResponse.ok([
            EntryWithGithubResponse.from_entity(e, push_map.get(entry_to_period(e)))
            for e in entries
        ])

    return ApiResponse.ok([EntryResponse.from_entity(e) for e in entries])


@router.get(
    "/paginated",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[EntryPageResponse],
)
async def get_entries_paginated(
    use_case: FromDishka[GetEntriesPageUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
    oauth_repo: FromDishka[IOAuthConnectionRepository],
    current_user: UserContext = Depends(get_current_user),
    retro_type: str = Query(alias="retroType"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=_MAX_ENTRY_PAGE_SIZE),
    q: str | None = Query(default=None, min_length=1),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> ApiResponse[EntryPageResponse]:
    """회고록 목록 페이지 — 최신순 페이지네이션(기본 10개씩).

    daily 는 journal_entries, weekly/monthly/annual 은 retro_summaries 에서 조회한다
    (소스 테이블이 달라 retroType 필수). from/to 있으면 기간 필터 — daily 는 date_key
    범위, summary 는 겹침(overlap) 기준(기간 일부라도 겹치면 포함).
    """
    if retro_type not in _VALID_RETRO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"retroType 은 {sorted(_VALID_RETRO_TYPES)} 중 하나여야 합니다.",
        )

    parse_date_range(from_date, to_date, _MAX_ENTRY_RANGE_DAYS)

    items_raw, total = await use_case.execute(
        GetEntriesPageQuery(
            user_id=current_user.id,
            retro_type=retro_type,
            page=page,
            size=size,
            q=q,
            from_date=from_date,
            to_date=to_date,
        )
    )

    is_dev_with_github = current_user.is_developer() and await _is_github_connected(
        oauth_repo, current_user.id
    )

    # EntryPageResponse.items 는 항상 EntryWithGithubResponse 로 통일한다(github_push
    # nullable) — get_entries 와 달리 두 응답 클래스를 섞으면 pydantic 이 직접 생성
    # 시점에 타입 불일치로 거부한다(FastAPI 의 response_model 관대한 재구성과 달리
    # 여기선 EntryPageResponse 를 직접 생성하므로).
    if retro_type == RetroType.DAILY.value:
        entries: list[JournalEntry] = items_raw  # type: ignore[assignment]
        push_map_e = (
            await _push_map_for_entries(push_repo, current_user.id, entries)
            if is_dev_with_github
            else {}
        )
        items = [
            EntryWithGithubResponse.from_entity(e, push_map_e.get(entry_to_period(e)))
            for e in entries
        ]
    else:
        summaries: list[RetroSummary] = items_raw  # type: ignore[assignment]
        push_map_s = (
            await _push_map_for_summaries(push_repo, current_user.id, summaries)
            if is_dev_with_github
            else {}
        )
        items = [
            EntryWithGithubResponse.from_summary(s, push_map_s.get(summary_to_period(s)))
            for s in summaries
        ]

    return ApiResponse.ok(EntryPageResponse(items=items, total=total, page=page, size=size))


@router.get(
    "/{entry_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[EntryWithGithubResponse],
)
async def get_entry(
    entry_id: str,
    use_case: FromDishka[GetEntryUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
    oauth_repo: FromDishka[IOAuthConnectionRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[EntryWithGithubResponse]:
    entry = await use_case.execute(entry_id=entry_id, user_id=current_user.id)

    if current_user.is_developer() and await _is_github_connected(oauth_repo, current_user.id):
        period_type, period_key = entry_to_period(entry)
        push = await push_repo.find_by_period(current_user.id, period_type, period_key)
        return ApiResponse.ok(EntryWithGithubResponse.from_entity(entry, push))

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
