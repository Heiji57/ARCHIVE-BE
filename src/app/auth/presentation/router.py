from fastapi import APIRouter, Request, Response, status

from app.auth.application.dtos.commands import (
    LoginCommand,
    RegisterCommand,
    SendEmailVerificationCommand,
    VerifyEmailCodeCommand,
)
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.register import RegisterUseCase
from app.auth.application.use_cases.send_email_verification import (
    SendEmailVerificationUseCase,
)
from app.auth.application.use_cases.verify_email_code import VerifyEmailCodeUseCase
from app.auth.presentation.requests.requests import (
    LoginRequest,
    RegisterRequest,
    SendVerificationRequest,
    VerifyCodeRequest,
)
from app.auth.presentation.responses.responses import PreAuthTokenResponse, TokenResponse
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


@router.post(
    "/email/verify/send",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def send_email_verification(
    body: SendVerificationRequest,
    request: Request,
) -> ApiResponse[None]:
    use_case: SendEmailVerificationUseCase = request.state.container.send_email_verification
    await use_case.execute(SendEmailVerificationCommand(email=body.email))
    return ApiResponse.ok(None)


@router.post(
    "/email/verify/confirm",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def verify_email_code(
    body: VerifyCodeRequest,
    request: Request,
) -> ApiResponse[None]:
    use_case: VerifyEmailCodeUseCase = request.state.container.verify_email_code
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
) -> ApiResponse[TokenResponse]:
    body.validate_passwords_match()
    use_case: RegisterUseCase = request.state.container.register
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
) -> ApiResponse[TokenResponse | PreAuthTokenResponse]:
    use_case: LoginUseCase = request.state.container.login
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
