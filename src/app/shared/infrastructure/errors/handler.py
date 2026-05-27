from fastapi.responses import JSONResponse

from app.auth.domain.exceptions.exceptions import (
    Auth2FACodeInvalidException,
    AuthInvalidCredentialsException,
    AuthTokenExpiredException,
    AuthTokenInvalidException,
    OAuthStateInvalidException,
    RefreshTokenInvalidException,
    RefreshTokenRevokedException,
)
from app.shared.domain.exceptions.base import BaseAppException
from app.user.domain.exceptions.exceptions import (
    UserEmailDuplicatedException,
    UserNotFoundException,
)

_STATUS_MAP: dict[str, int] = {
    # 400
    AuthTokenInvalidException.code: 400,
    OAuthStateInvalidException.code: 400,
    # 401
    AuthTokenExpiredException.code: 401,
    AuthInvalidCredentialsException.code: 401,
    RefreshTokenInvalidException.code: 401,
    RefreshTokenRevokedException.code: 401,
    Auth2FACodeInvalidException.code: 401,
    # 404
    UserNotFoundException.code: 404,
    # 409
    UserEmailDuplicatedException.code: 409,
}


def to_http_response(exc: BaseAppException) -> JSONResponse:
    status_code = _STATUS_MAP.get(exc.code, 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "code": exc.code,
            "data": None,
            "details": exc.details,
        },
    )
