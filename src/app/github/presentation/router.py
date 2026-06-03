from datetime import date

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.github.application.dtos.commands import (
    LinkRepositoryCommand,
    PushRetrospectiveCommand,
    SyncAllRepositoriesCommand,
    UnlinkRepositoryCommand,
)
from app.github.application.use_cases.get_connection_status import GetConnectionStatusUseCase
from app.github.application.use_cases.get_today_commits import GetTodayCommitsUseCase
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
from app.github.presentation.requests.requests import (
    LinkRepositoryRequest,
    PushRetrospectiveRequest,
    UpdateRepositoryRequest,
)
from app.github.presentation.responses.responses import (
    AvailableRepositoryResponse,
    CommitResponse,
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
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[RepositoryResponse]:
    repo = await use_case.execute(
        LinkRepositoryCommand(user_id=current_user.id, github_repo_id=body.github_repo_id)
    )
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
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[RepositoryResponse]:
    repo = await use_case.execute(
        UpdateRepositoryCommand(
            user_id=current_user.id,
            repository_id=repository_id,
            commit_read_enabled=body.commit_read_enabled,
        )
    )
    return ApiResponse.ok(RepositoryResponse.from_entity(repo))


@router.post(
    "/repositories/sync-all",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[RepositoryResponse]],
)
async def sync_all_repositories(
    use_case: FromDishka[SyncAllRepositoriesUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[RepositoryResponse]]:
    repos = await use_case.execute(SyncAllRepositoriesCommand(user_id=current_user.id))
    return ApiResponse.ok([RepositoryResponse.from_entity(r) for r in repos])


@router.delete(
    "/repositories/{repository_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def unlink_repository(
    repository_id: str,
    use_case: FromDishka[UnlinkRepositoryUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(
        UnlinkRepositoryCommand(user_id=current_user.id, repository_id=repository_id)
    )
    return ApiResponse.ok(None)


@router.delete(
    "/repositories",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def unlink_all_repositories(
    use_case: FromDishka[UnlinkAllRepositoriesUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(current_user.id)
    return ApiResponse.ok(None)


# ── Commits ────────────────────────────────────────────────────────────────

@router.get(
    "/commits",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[CommitResponse]],
)
async def get_today_commits(
    use_case: FromDishka[GetTodayCommitsUseCase],
    target_date: date | None = Query(default=None, alias="date"),
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[CommitResponse]]:
    commits = await use_case.execute(current_user.id, target_date)
    return ApiResponse.ok([CommitResponse.from_commit(c) for c in commits])


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
