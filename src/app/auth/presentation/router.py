from fastapi import APIRouter, Depends, Request, Response, status
from dishka.integrations.fastapi import FromDishka

from app.auth.application.dtos.commands import (
    LoginCommand,
    RegisterCommand,
    SendEmailVerificationCommand,
    VerifyEmailCodeCommand,
)
from app.auth.application.use_cases.get_me import GetMeUseCase
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.application.use_cases.refresh_token import RefreshTokenUseCase
from app.auth.application.use_cases.register import RegisterUseCase
from app.auth.application.use_cases.send_email_verification import SendEmailVerificationUseCase
from app.auth.application.use_cases.update_profile import UpdateProfileCommand, UpdateProfileUseCase
from app.auth.application.use_cases.verify_email_code import VerifyEmailCodeUseCase
from app.auth.presentation.requests.requests import (
    LoginRequest,
    RegisterRequest,
    SendVerificationRequest,
    UpdateProfileRequest,
    VerifyCodeRequest,
)
from app.auth.presentation.responses.responses import PreAuthTokenResponse, TokenResponse, UserResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import extract_refresh_token, get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7일


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE, httponly=True, secure=True, samesite="lax")


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
    body.validate_passwords_match()
    result = await use_case.execute(
        RegisterCommand(
            email=body.email,
            password=body.password,
            device_info=request.headers.get("user-agent"),
        )
    )
    _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.created(TokenResponse(access_token=result["access_token"]))


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TokenResponse | PreAuthTokenResponse],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    use_case: FromDishka[LoginUseCase],
) -> ApiResponse[TokenResponse | PreAuthTokenResponse]:
    result = await use_case.execute(
        LoginCommand(
            email=body.email,
            password=body.password,
            device_info=request.headers.get("user-agent"),
        )
    )
    if "pre_auth_token" in result:
        return ApiResponse.ok(PreAuthTokenResponse(pre_auth_token=result["pre_auth_token"]))

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
    raw_refresh: str = Depends(extract_refresh_token),
    use_case: FromDishka[RefreshTokenUseCase] = ...,  # type: ignore[assignment]
) -> ApiResponse[TokenResponse]:
    result = await use_case.execute(
        raw_refresh_token=raw_refresh,
        device_info=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.ok(TokenResponse(access_token=result["access_token"]))


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def logout(
    response: Response,
    current_user: UserContext = Depends(get_current_user),
    raw_refresh: str = Depends(extract_refresh_token),
    use_case: FromDishka[LogoutUseCase] = ...,  # type: ignore[assignment]
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
    current_user: UserContext = Depends(get_current_user),
    use_case: FromDishka[GetMeUseCase] = ...,  # type: ignore[assignment]
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
    current_user: UserContext = Depends(get_current_user),
    use_case: FromDishka[UpdateProfileUseCase] = ...,  # type: ignore[assignment]
) -> ApiResponse[UserResponse]:
    user = await use_case.execute(
        UpdateProfileCommand(user_id=current_user.id, display_name=body.display_name)
    )
    return ApiResponse.ok(UserResponse.from_entity(user))
