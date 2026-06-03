from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, status

from app.github.application.dtos.commands import (
    LinkRepositoryCommand,
    SyncAllRepositoriesCommand,
    UnlinkRepositoryCommand,
)
from app.github.application.use_cases.link_repository import LinkRepositoryUseCase
from app.github.application.use_cases.list_available_repositories import (
    ListAvailableRepositoriesUseCase,
)
from app.github.application.use_cases.list_linked_repositories import (
    ListLinkedRepositoriesUseCase,
)
from app.github.application.use_cases.sync_all_repositories import SyncAllRepositoriesUseCase
from app.github.application.use_cases.unlink_all_repositories import UnlinkAllRepositoriesUseCase
from app.github.application.use_cases.unlink_repository import UnlinkRepositoryUseCase
from app.github.presentation.requests.requests import LinkRepositoryRequest
from app.github.presentation.responses.responses import (
    AvailableRepositoryResponse,
    RepositoryResponse,
)
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/github/repositories", tags=["github"], route_class=DishkaRoute)


@router.get(
    "/available",
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
    "",
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
    "",
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


@router.post(
    "/sync-all",
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
    "/{repository_id}",
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
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def unlink_all_repositories(
    use_case: FromDishka[UnlinkAllRepositoriesUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(current_user.id)
    return ApiResponse.ok(None)
