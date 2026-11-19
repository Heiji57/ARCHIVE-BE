from datetime import date

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.github.application.dtos.commands import (
    LinkRepositoryCommand,
    PushRetrospectiveCommand,
    SyncAllRepositoriesCommand,
    UnlinkRepositoryCommand,
)
from app.github.application.use_cases.get_commits_by_date import (
    MAX_RANGE_DAYS,
    GetCommitsByDateUseCase,
)
from app.github.application.use_cases.get_connection_status import GetConnectionStatusUseCase
from app.github.application.use_cases.link_repository import LinkRepositoryUseCase
from app.github.application.use_cases.list_available_repositories import (
    ListAvailableRepositoriesUseCase,
)
from app.github.application.use_cases.list_linked_repositories import (
    ListLinkedRepositoriesUseCase,
)
from app.github.application.use_cases.push_retrospective import PushRetrospectiveUseCase
from app.github.application.use_cases.sync_all_repositories import SyncAllRepositoriesUseCase
from app.github.application.use_cases.unlink_all_repositories import UnlinkAllRepositoriesUseCase
from app.github.application.use_cases.unlink_repository import UnlinkRepositoryUseCase
from app.github.application.use_cases.update_repository import (
    UpdateRepositoryCommand,
    UpdateRepositoryUseCase,
)
from app.github.domain.exceptions.exceptions import (
    GitHubCommitQueryInvalidException,
    GitHubRangeTooLongException,
)
from app.github.domain.repositories.repository import ICommitDayCache
from app.github.presentation.requests.requests import (
    LinkRepositoryRequest,
    PushRetrospectiveRequest,
    UpdateRepositoryRequest,
)
from app.github.presentation.responses.responses import (
    AvailableRepositoryResponse,
    CommitListResponse,
    ConnectionStatusResponse,
    PushResultResponse,
    RepositoryResponse,
)
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/github", tags=["github"], route_class=DishkaRoute)


# ── Connection ─────────────────────────────────────────────────────────────

@router.get(
    "/connection",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[ConnectionStatusResponse],
)
async def get_connection_status(
    use_case: FromDishka[GetConnectionStatusUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ConnectionStatusResponse]:
    status_data = await use_case.execute(current_user.id)
    return ApiResponse.ok(ConnectionStatusResponse.from_status(status_data))


# ── Repositories ───────────────────────────────────────────────────────────

@router.get(
    "/repositories/available",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[AvailableRepositoryResponse]],
)
async def list_available_repositories(
    use_case: FromDishka[ListAvailableRepositoriesUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[AvailableRepositoryResponse]]:
    repos = await use_case.execute(current_user.id)
    return ApiResponse.ok([AvailableRepositoryResponse.from_data(r) for r in repos])


@router.get(
    "/repositories",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[RepositoryResponse]],
)
async def list_linked_repositories(
    use_case: FromDishka[ListLinkedRepositoriesUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[RepositoryResponse]]:
    repos = await use_case.execute(current_user.id)
    return ApiResponse.ok([RepositoryResponse.from_entity(r) for r in repos])


@router.post(
    "/repositories",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[RepositoryResponse],
)
async def link_repository(
    body: LinkRepositoryRequest,
    use_case: FromDishka[LinkRepositoryUseCase],
    commit_cache: FromDishka[ICommitDayCache],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[RepositoryResponse]:
    repo = await use_case.execute(
        LinkRepositoryCommand(user_id=current_user.id, github_repo_id=body.github_repo_id)
    )
    await commit_cache.invalidate_user(current_user.id)
    return ApiResponse.created(RepositoryResponse.from_entity(repo))


@router.patch(
    "/repositories/{repository_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[RepositoryResponse],
)
async def update_repository(
    repository_id: str,
    body: UpdateRepositoryRequest,
    use_case: FromDishka[UpdateRepositoryUseCase],
    commit_cache: FromDishka[ICommitDayCache],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[RepositoryResponse]:
    repo = await use_case.execute(
        UpdateRepositoryCommand(
            user_id=current_user.id,
            repository_id=repository_id,
            commit_read_enabled=body.commit_read_enabled,
        )
    )
    await commit_cache.invalidate_user(current_user.id)
    return ApiResponse.ok(RepositoryResponse.from_entity(repo))


@router.post(
    "/repositories/sync-all",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[RepositoryResponse]],
)
async def sync_all_repositories(
    use_case: FromDishka[SyncAllRepositoriesUseCase],
    commit_cache: FromDishka[ICommitDayCache],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[RepositoryResponse]]:
    repos = await use_case.execute(SyncAllRepositoriesCommand(user_id=current_user.id))
    await commit_cache.invalidate_user(current_user.id)
    return ApiResponse.ok([RepositoryResponse.from_entity(r) for r in repos])


@router.delete(
    "/repositories/{repository_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def unlink_repository(
    repository_id: str,
    use_case: FromDishka[UnlinkRepositoryUseCase],
    commit_cache: FromDishka[ICommitDayCache],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(
        UnlinkRepositoryCommand(user_id=current_user.id, repository_id=repository_id)
    )
    await commit_cache.invalidate_user(current_user.id)
    return ApiResponse.ok(None)


@router.delete(
    "/repositories",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def unlink_all_repositories(
    use_case: FromDishka[UnlinkAllRepositoriesUseCase],
    commit_cache: FromDishka[ICommitDayCache],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(current_user.id)
    await commit_cache.invalidate_user(current_user.id)
    return ApiResponse.ok(None)


# ── Commits ────────────────────────────────────────────────────────────────

@router.get(
    "/commits",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[CommitListResponse],
)
async def get_commits(
    use_case: FromDishka[GetCommitsByDateUseCase],
    target_date: date | None = Query(default=None, alias="date"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[CommitListResponse]:
    """`date` 하루(기본 오늘) 또는 `from`~`to` 기간(사용자 tz, 포함, 최대 31일)."""
    if target_date is not None and (from_date or to_date):
        raise GitHubCommitQueryInvalidException("date and from/to cannot be combined.")
    if (from_date is None) != (to_date is None):
        raise GitHubCommitQueryInvalidException("from and to must be sent together.")
    if from_date is not None and to_date is not None:
        if from_date > to_date:
            raise GitHubCommitQueryInvalidException("from must not be after to.")
        if (to_date - from_date).days + 1 > MAX_RANGE_DAYS:
            raise GitHubRangeTooLongException(f"Commit range is limited to {MAX_RANGE_DAYS} days.")
        result = await use_case.execute(current_user.id, from_date, to_date)
    else:
        result = await use_case.execute(current_user.id, target_date, target_date)
    return ApiResponse.ok(CommitListResponse.from_result(result))


# ── Retrospectives Push ────────────────────────────────────────────────────

@router.post(
    "/retrospectives/push",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[PushResultResponse],
)
async def push_retrospective(
    body: PushRetrospectiveRequest,
    use_case: FromDishka[PushRetrospectiveUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[PushResultResponse]:
    outcome = await use_case.execute(
        PushRetrospectiveCommand(
            user_id=current_user.id,
            period_type=body.period_type,
            period_key=body.period_key,
            content_markdown=body.content_markdown,
        )
    )
    return ApiResponse.created(PushResultResponse.from_outcome(outcome))
