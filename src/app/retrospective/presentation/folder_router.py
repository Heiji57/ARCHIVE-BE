from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.domain.repositories.retrospective_push_repository import (
    IRetrospectivePushRepository,
)
from app.github.domain.utils.period_mapping import entry_to_period, summary_to_period
from app.retrospective.application.dtos.folder_commands import (
    UNSET,
    CreateFolderCommand,
    DeleteFolderCommand,
    UpdateFolderCommand,
)
from app.retrospective.application.dtos.folder_queries import GetFolderContentsQuery
from app.retrospective.application.use_cases.create_folder import CreateFolderUseCase
from app.retrospective.application.use_cases.delete_folder import DeleteFolderUseCase
from app.retrospective.application.use_cases.get_folder_contents import (
    GetFolderContentsUseCase,
)
from app.retrospective.application.use_cases.update_folder import UpdateFolderUseCase
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.presentation.requests.folder_requests import (
    FolderCreateRequest,
    FolderUpdateRequest,
)
from app.retrospective.presentation.responses.folder_responses import (
    FolderContentsResponse,
    FolderResponse,
)
from app.retrospective.presentation.responses.responses import EntryWithGithubResponse
from app.retrospective.presentation.router import _is_github_connected, _push_map_for_entries, _push_map_for_summaries
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/folders", tags=["folders"], route_class=DishkaRoute)

_VALID_RETRO_TYPES = {t.value for t in RetroType}
_MAX_CONTENTS_PAGE_SIZE = 50


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FolderResponse],
)
async def create_folder(
    body: FolderCreateRequest,
    use_case: FromDishka[CreateFolderUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[FolderResponse]:
    folder = await use_case.execute(
        CreateFolderCommand(
            user_id=current_user.id,
            name=body.name,
            parent_folder_id=body.parent_folder_id,
        )
    )
    return ApiResponse.created(FolderResponse.from_entity(folder))


@router.get(
    "/contents",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[FolderContentsResponse],
)
async def get_folder_contents(
    use_case: FromDishka[GetFolderContentsUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
    oauth_repo: FromDishka[IOAuthConnectionRepository],
    current_user: UserContext = Depends(get_current_user),
    folder_id: str | None = Query(default=None, alias="folderId"),
    retro_type: str | None = Query(default=None, alias="retroType"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=_MAX_CONTENTS_PAGE_SIZE),
) -> ApiResponse[FolderContentsResponse]:
    """폴더 열람 — 직계 하위 폴더(folders)와 직계 회고록(entries)을 분리해서 반환.

    retroType 미지정 시 daily(journal_entries) + weekly/monthly/yearly
    (retro_summaries) 를 합쳐 최신순으로 정렬한 "전체" 뷰.

    page/size 는 폴더와 회고록을 합친 하나의 시퀀스
    (`[폴더: name ASC, id ASC] ++ [회고록: 날짜 DESC, id DESC]`)에 대한
    오프셋이다 — 폴더 블록이 먼저 소진된 뒤 회고록이 이어진다. 따라서
    folders 는 이 페이지 구간에 걸친 폴더 조각이고(직계 하위 폴더 전부가
    아니다), total 은 폴더 총개수 + 회고록 총건수다.
    """
    if retro_type is not None and retro_type not in _VALID_RETRO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"retroType 은 {sorted(_VALID_RETRO_TYPES)} 중 하나여야 합니다.",
        )

    subfolders, items, total = await use_case.execute(
        GetFolderContentsQuery(
            user_id=current_user.id,
            folder_id=folder_id,
            retro_type=retro_type,
            page=page,
            size=size,
        )
    )

    is_dev_with_github = current_user.is_developer() and await _is_github_connected(
        oauth_repo, current_user.id
    )

    entries = [i for i in items if isinstance(i, JournalEntry)]
    summaries = [i for i in items if not isinstance(i, JournalEntry)]
    push_map_e = (
        await _push_map_for_entries(push_repo, current_user.id, entries)
        if is_dev_with_github
        else {}
    )
    push_map_s = (
        await _push_map_for_summaries(push_repo, current_user.id, summaries)
        if is_dev_with_github
        else {}
    )

    # 원래 정렬 순서(최신순) 유지하며 응답 아이템으로 매핑
    entry_items = []
    for item in items:
        if isinstance(item, JournalEntry):
            entry_items.append(
                EntryWithGithubResponse.from_entity(item, push_map_e.get(entry_to_period(item)))
            )
        else:
            entry_items.append(
                EntryWithGithubResponse.from_summary(item, push_map_s.get(summary_to_period(item)))
            )

    return ApiResponse.ok(
        FolderContentsResponse(
            folders=[FolderResponse.from_with_counts(f) for f in subfolders],
            entries=entry_items,
            total=total,
            page=page,
            size=size,
        )
    )


@router.patch(
    "/{folder_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[FolderResponse],
)
async def update_folder(
    folder_id: str,
    body: FolderUpdateRequest,
    use_case: FromDishka[UpdateFolderUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[FolderResponse]:
    provided = body.model_fields_set
    folder = await use_case.execute(
        UpdateFolderCommand(
            folder_id=folder_id,
            user_id=current_user.id,
            name=body.name,
            parent_folder_id=(
                body.parent_folder_id if "parent_folder_id" in provided else UNSET
            ),
        )
    )
    return ApiResponse.ok(FolderResponse.from_entity(folder))


@router.delete(
    "/{folder_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def delete_folder(
    folder_id: str,
    use_case: FromDishka[DeleteFolderUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(DeleteFolderCommand(folder_id=folder_id, user_id=current_user.id))
    return ApiResponse.ok(None)
