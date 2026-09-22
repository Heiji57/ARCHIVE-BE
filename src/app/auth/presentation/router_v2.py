"""auth v2 — v1 에서 한 코드로 뭉개지던 실패를 세분화된 에러 코드로 내보내는 엔드포인트.

요청/응답 본문은 v1 과 동일하고 에러 코드만 다르다. 코드 선택은 전역 핸들러가 경로
prefix(`/api/v2/`)로 하므로, 이메일 인증은 v1 핸들러 함수를 그대로 재사용한다.
OAuth 는 callback 이 v1 경로에 고정(provider 에 등록된 redirect_uri)이라, 흐름을 시작하는
authorize/link-init 만 v2 로 두고 state 에 버전을 기록한다.
"""
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse

from app.auth.application.use_cases.initiate_oauth import InitiateOAuthUseCase
from app.auth.application.use_cases.initiate_oauth_link import InitiateOAuthLinkUseCase
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.presentation.responses.responses import OAuthLinkInitResponse
from app.auth.presentation.router import send_email_verification, verify_email_code
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth-v2"], route_class=DishkaRoute)

router.add_api_route(
    "/email/verify/send",
    send_email_verification,
    methods=["POST"],
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
router.add_api_route(
    "/email/verify/confirm",
    verify_email_code,
    methods=["POST"],
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)


@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: OAuthProvider,
    use_case: FromDishka[InitiateOAuthUseCase],
) -> RedirectResponse:
    redirect_url = await use_case.execute(provider, api_version="v2")
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.post(
    "/oauth/{provider}/link/init",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[OAuthLinkInitResponse],
)
async def oauth_link_init(
    provider: OAuthProvider,
    use_case: FromDishka[InitiateOAuthLinkUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[OAuthLinkInitResponse]:
    authorize_url = await use_case.execute(provider, current_user.id, api_version="v2")
    return ApiResponse.ok(OAuthLinkInitResponse(authorize_url=authorize_url))
