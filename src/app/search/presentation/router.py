from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.search.application.use_cases.global_search import GlobalSearchUseCase, SearchScope
from app.search.presentation.responses.responses import GlobalSearchResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/search", tags=["search"], route_class=DishkaRoute)

_MAX_SEARCH_LIMIT = 20


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[GlobalSearchResponse],
)
async def global_search(
    use_case: FromDishka[GlobalSearchUseCase],
    current_user: UserContext = Depends(get_current_user),
    q: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=_MAX_SEARCH_LIMIT),
    scope: SearchScope = Query(default="all"),
) -> ApiResponse[GlobalSearchResponse]:
    """통합검색 — scope 에 따라 Todo / 회고(모든 종류) / 주제 검색(종류별 상위 `limit`개)."""
    result = await use_case.execute(current_user.id, q, limit, scope)
    return ApiResponse.ok(GlobalSearchResponse.from_result(result))
