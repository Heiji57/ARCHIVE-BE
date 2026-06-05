import json

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.application.dtos.commands import (
    CompleteOnboardingCommand,
    LoginCommand,
    RegisterCommand,
    RequestPasswordResetCommand,
    ResetPasswordCommand,
    SendEmailVerificationCommand,
    VerifyEmailCodeCommand,
)
from app.auth.application.services.session_service import SessionService
from app.auth.application.use_cases.complete_onboarding import CompleteOnboardingUseCase
from app.auth.application.use_cases.initiate_oauth_link import InitiateOAuthLinkUseCase
from app.auth.application.use_cases.list_sessions import ListSessionsUseCase
from app.auth.application.use_cases.request_password_reset import RequestPasswordResetUseCase
from app.auth.application.use_cases.reset_password import ResetPasswordUseCase
from app.auth.application.use_cases.revoke_session import (
    RevokeOtherSessionsUseCase,
    RevokeSessionUseCase,
)
from app.auth.application.use_cases.get_me import GetMeUseCase
from app.auth.application.use_cases.handle_oauth_callback import HandleOAuthCallbackUseCase
from app.auth.application.use_cases.initiate_oauth import InitiateOAuthUseCase
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.application.use_cases.refresh_token import RefreshTokenUseCase
from app.auth.application.use_cases.register import RegisterUseCase
from app.auth.application.use_cases.send_email_verification import SendEmailVerificationUseCase
from app.auth.application.use_cases.update_profile import UpdateProfileCommand, UpdateProfileUseCase
from app.auth.application.use_cases.verify_email_code import VerifyEmailCodeUseCase
from app.auth.domain.exceptions.exceptions import OnboardingTokenInvalidException
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.presentation.requests.requests import (
    LoginRequest,
    OnboardingCompleteRequest,
    RegisterRequest,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    SendVerificationRequest,
    UpdateProfileRequest,
    VerifyCodeRequest,
)
from app.auth.presentation.responses.responses import (
    OAuthLinkInitResponse,
    TokenResponse,
    UserResponse,
)
from app.auth.presentation.responses.session_responses import (
    RevokeOthersResponse,
    SessionListResponse,
    SessionResponse,
)
from app.shared.domain.context.user_context import UserContext
from app.shared.domain.exceptions.base import BaseAppException
from app.shared.infrastructure.auth.jwt import extract_refresh_token, get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"], route_class=DishkaRoute)

_REFRESH_COOKIE = "refresh_token"
_ONBOARDING_COOKIE = "onboarding_token"


def _refresh_cookie_max_age() -> int:
    return get_settings().auth.refresh_token_expire_days * 86400


def _onboarding_cookie_max_age() -> int:
    return get_settings().auth.onboarding_token_ttl_seconds


def _client_ip(request: Request) -> str | None:
    """프록시 뒤에서 동작 가능하도록 X-Forwarded-For 우선."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_refresh_cookie_max_age(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE, httponly=True, secure=True, samesite="lax")


def _set_onboarding_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_ONBOARDING_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_onboarding_cookie_max_age(),
        path="/",
    )


def _clear_onboarding_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_ONBOARDING_COOKIE, httponly=True, secure=True, samesite="lax"
    )


def _oauth_success_html(access_token: str, frontend_origin: str) -> str:
    message = json.dumps({"type": "oauth_success", "access_token": access_token})
    origin = json.dumps(frontend_origin)
    return f"""<!DOCTYPE html>
<html><head><title>OAuth</title></head><body><script>
  if (window.opener) {{ window.opener.postMessage({message}, {origin}); window.close(); }}
  else {{ window.location.href = {origin}; }}
</script></body></html>"""


def _oauth_onboarding_html(frontend_origin: str) -> str:
    message = json.dumps({"type": "oauth_onboarding_required"})
    origin = json.dumps(frontend_origin)
    return f"""<!DOCTYPE html>
<html><head><title>OAuth Onboarding</title></head><body><script>
  if (window.opener) {{ window.opener.postMessage({message}, {origin}); window.close(); }}
  else {{ window.location.href = {origin} + '/onboarding'; }}
</script></body></html>"""


def _oauth_linked_html(provider: str, frontend_origin: str) -> str:
    message = json.dumps({"type": "oauth_linked", "provider": provider})
    origin = json.dumps(frontend_origin)
    return f"""<!DOCTYPE html>
<html><head><title>OAuth Linked</title></head><body><script>
  if (window.opener) {{ window.opener.postMessage({message}, {origin}); window.close(); }}
  else {{ window.location.href = {origin} + '/settings'; }}
</script></body></html>"""


def _oauth_error_html(error_code: str, frontend_origin: str) -> str:
    message = json.dumps({"type": "oauth_error", "error": error_code})
    origin = json.dumps(frontend_origin)
    return f"""<!DOCTYPE html>
<html><head><title>OAuth Error</title></head><body><script>
  if (window.opener) {{ window.opener.postMessage({message}, {origin}); window.close(); }}
  else {{ window.location.href = {origin}; }}
</script></body></html>"""


@router.post(
    "/email/verify/send",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def send_email_verification(
    body: SendVerificationRequest,
    use_case: FromDishka[SendEmailVerificationUseCase],
) -> ApiResponse[None]:
    await use_case.execute(SendEmailVerificationCommand(email=body.email))
    return ApiResponse.ok(None)


@router.post(
    "/email/verify/confirm",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def verify_email_code(
    body: VerifyCodeRequest,
    use_case: FromDishka[VerifyEmailCodeUseCase],
) -> ApiResponse[None]:
    await use_case.execute(VerifyEmailCodeCommand(email=body.email, code=body.code))
    return ApiResponse.ok(None)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TokenResponse],
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    use_case: FromDishka[RegisterUseCase],
) -> ApiResponse[TokenResponse]:
    result = await use_case.execute(
        RegisterCommand(
            email=body.email,
            password=body.password,
            country=body.country,
            region=body.region,
            device_info=request.headers.get("user-agent"),
            ip=_client_ip(request),
        )
    )
    _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.created(TokenResponse(access_token=result["access_token"]))


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TokenResponse],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    use_case: FromDishka[LoginUseCase],
) -> ApiResponse[TokenResponse]:
    result = await use_case.execute(
        LoginCommand(
            email=body.email,
            password=body.password,
            device_info=request.headers.get("user-agent"),
            ip=_client_ip(request),
        )
    )
    _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.ok(TokenResponse(access_token=result["access_token"]))


@router.post(
    "/token/refresh",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TokenResponse],
)
async def refresh_token(
    request: Request,
    response: Response,
    use_case: FromDishka[RefreshTokenUseCase],
    raw_refresh: str = Depends(extract_refresh_token),
) -> ApiResponse[TokenResponse]:
    result = await use_case.execute(
        raw_refresh_token=raw_refresh,
        device_info=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )
    # 빈 refresh_token = grace window hit (동시 refresh race) — 기존 쿠키 유지
    if result["refresh_token"]:
        _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.ok(TokenResponse(access_token=result["access_token"]))


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def logout(
    response: Response,
    use_case: FromDishka[LogoutUseCase],
    current_user: UserContext = Depends(get_current_user),
    raw_refresh: str = Depends(extract_refresh_token),
) -> ApiResponse[None]:
    await use_case.execute(user_id=current_user.id, raw_refresh_token=raw_refresh)
    _clear_refresh_cookie(response)
    return ApiResponse.ok(None)


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UserResponse],
)
async def get_me(
    use_case: FromDishka[GetMeUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[UserResponse]:
    user = await use_case.execute(current_user.id)
    return ApiResponse.ok(UserResponse.from_entity(user))


@router.patch(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UserResponse],
)
async def update_profile(
    body: UpdateProfileRequest,
    use_case: FromDishka[UpdateProfileUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[UserResponse]:
    user = await use_case.execute(
        UpdateProfileCommand(user_id=current_user.id, display_name=body.display_name)
    )
    return ApiResponse.ok(UserResponse.from_entity(user))


@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: OAuthProvider,
    use_case: FromDishka[InitiateOAuthUseCase],
) -> RedirectResponse:
    redirect_url = await use_case.execute(provider)
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: OAuthProvider,
    request: Request,
    use_case: FromDishka[HandleOAuthCallbackUseCase],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> HTMLResponse:
    frontend_origin = get_settings().frontend_url

    if error or not code or not state:
        return HTMLResponse(content=_oauth_error_html(error or "missing_params", frontend_origin))

    try:
        result = await use_case.execute(
            provider=provider,
            code=code,
            state=state,
            device_info=request.headers.get("user-agent"),
            ip=_client_ip(request),
        )
    except BaseAppException as e:
        return HTMLResponse(content=_oauth_error_html(e.code, frontend_origin))
    except Exception:
        return HTMLResponse(content=_oauth_error_html("INTERNAL_ERROR", frontend_origin))

    if result.kind == "onboarding":
        # 신규 사용자 — onboarding cookie 발급 + FE 온보딩 페이지로 안내
        html_response = HTMLResponse(content=_oauth_onboarding_html(frontend_origin))
        html_response.set_cookie(
            key=_ONBOARDING_COOKIE,
            value=result.onboarding_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=_onboarding_cookie_max_age(),
            path="/",
        )
        return html_response

    if result.kind == "linked":
        # 계정 link 성공 — 새 세션 발급 없음, FE에 link 완료 신호만
        return HTMLResponse(
            content=_oauth_linked_html(result.linked_provider or provider.value, frontend_origin)
        )

    # 기존 사용자 — refresh cookie + access_token postMessage (kind == "login")
    html_response = HTMLResponse(content=_oauth_success_html(result.access_token, frontend_origin))
    html_response.set_cookie(
        key=_REFRESH_COOKIE,
        value=result.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_refresh_cookie_max_age(),
    )
    return html_response


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
    """로그인된 사용자가 OAuth provider 계정 link 흐름을 시작.

    Bearer 인증 필수. 응답의 authorizeUrl 을 FE 가 popup 으로 직접 열면,
    GitHub/Google 의 동의 화면을 거쳐 기존 callback 으로 돌아오고, state 에 저장된
    link_user_id 로 link 분기가 작동한다.
    """
    authorize_url = await use_case.execute(provider, current_user.id)
    return ApiResponse.ok(OAuthLinkInitResponse(authorize_url=authorize_url))


@router.post(
    "/password/reset/request",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def request_password_reset(
    body: RequestPasswordResetRequest,
    use_case: FromDishka[RequestPasswordResetUseCase],
) -> ApiResponse[None]:
    """비밀번호 재설정 요청.

    이메일 enumeration 방지를 위해 결과(존재 여부)와 무관하게 항상 200을 반환한다.
    내부적으로 등록된 이메일 + 비밀번호 보유 + 쿨다운 통과 시에만 메일 발송.
    """
    await use_case.execute(RequestPasswordResetCommand(email=body.email))
    return ApiResponse.ok(None)


@router.post(
    "/password/reset/confirm",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def reset_password_confirm(
    body: ResetPasswordRequest,
    use_case: FromDishka[ResetPasswordUseCase],
) -> ApiResponse[None]:
    """비밀번호 재설정 확정.

    성공 시 사용자의 모든 활성 refresh token이 폐기된다 — 다른 기기 강제 로그아웃.
    """
    await use_case.execute(
        ResetPasswordCommand(token=body.token, new_password=body.new_password)
    )
    return ApiResponse.ok(None)


@router.post(
    "/oauth/onboarding",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TokenResponse],
)
async def oauth_onboarding(
    body: OnboardingCompleteRequest,
    request: Request,
    response: Response,
    use_case: FromDishka[CompleteOnboardingUseCase],
    onboarding_token: str | None = Cookie(default=None, alias=_ONBOARDING_COOKIE),
) -> ApiResponse[TokenResponse]:
    if not onboarding_token:
        raise OnboardingTokenInvalidException("Onboarding cookie missing")

    result = await use_case.execute(
        CompleteOnboardingCommand(
            onboarding_token=onboarding_token,
            country=body.country,
            region=body.region,
            device_info=request.headers.get("user-agent"),
            ip=_client_ip(request),
        )
    )
    _clear_onboarding_cookie(response)
    _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.created(TokenResponse(access_token=result["access_token"]))


# ── 세션 관리 API ──────────────────────────────────────────────────────────────


@router.get(
    "/sessions",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SessionListResponse],
)
async def list_sessions(
    use_case: FromDishka[ListSessionsUseCase],
    session_service: FromDishka[SessionService],
    current_user: UserContext = Depends(get_current_user),
    raw_refresh: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> ApiResponse[SessionListResponse]:
    """현재 사용자의 활성 세션 목록. is_current 로 현재 세션 식별."""
    current_sid = (
        await session_service.get_session_id_from_rt(raw_refresh) if raw_refresh else None
    )
    views = await use_case.execute(current_user.id, current_sid)
    return ApiResponse.ok(
        SessionListResponse(sessions=[SessionResponse.from_view(v) for v in views])
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def revoke_session(
    session_id: str,
    use_case: FromDishka[RevokeSessionUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    """단일 세션 폐기. 현재 세션을 폐기하면 다음 요청부터 401."""
    await use_case.execute(current_user.id, session_id)
    return ApiResponse.ok(None)


@router.delete(
    "/sessions",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[RevokeOthersResponse],
)
async def revoke_other_sessions(
    use_case: FromDishka[RevokeOtherSessionsUseCase],
    session_service: FromDishka[SessionService],
    current_user: UserContext = Depends(get_current_user),
    raw_refresh: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> ApiResponse[RevokeOthersResponse]:
    """현재 세션을 제외한 모든 세션 폐기 (= 다른 기기 전부 로그아웃)."""
    current_sid = (
        await session_service.get_session_id_from_rt(raw_refresh) if raw_refresh else None
    )
    revoked = (
        await use_case.execute(current_user.id, current_sid) if current_sid else 0
    )
    return ApiResponse.ok(RevokeOthersResponse(revoked_count=revoked))
