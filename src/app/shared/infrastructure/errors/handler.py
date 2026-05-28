from fastapi import Request
from fastapi.exceptions import RequestValidationError
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
from app.notification.domain.exceptions.exceptions import NotificationNotFoundException
from app.retrospective.domain.exceptions.exceptions import (
    JournalEntryAlreadyExistsException,
    JournalEntryNotFoundException,
    RetroSummaryNotFoundException,
    SummaryAlreadyInProgressException,
    SummaryInvalidStateException,
)
from app.shared.domain.exceptions.base import BaseAppException
from app.todo.domain.exceptions.exceptions import (
    TodoAlreadyCompletedException,
    TodoAlreadyInProgressException,
    TodoNotFoundException,
)
from app.user.domain.exceptions.exceptions import (
    UserEmailDuplicatedException,
    UserNotFoundException,
)

_STATUS_MAP: dict[str, int] = {
    # 400
    AuthTokenInvalidException.code: 400,
    OAuthStateInvalidException.code: 400,
    SummaryInvalidStateException.code: 400,
    # 401
    AuthTokenExpiredException.code: 401,
    AuthInvalidCredentialsException.code: 401,
    RefreshTokenInvalidException.code: 401,
    RefreshTokenRevokedException.code: 401,
    Auth2FACodeInvalidException.code: 401,
    # 404
    UserNotFoundException.code: 404,
    TodoNotFoundException.code: 404,
    JournalEntryNotFoundException.code: 404,
    RetroSummaryNotFoundException.code: 404,
    NotificationNotFoundException.code: 404,
    # 409
    UserEmailDuplicatedException.code: 409,
    TodoAlreadyCompletedException.code: 409,
    TodoAlreadyInProgressException.code: 409,
    JournalEntryAlreadyExistsException.code: 409,
    SummaryAlreadyInProgressException.code: 409,
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


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(loc) for loc in err["loc"] if loc != "body"), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "code": "VALIDATION_ERROR",
            "data": None,
            "details": details,
        },
    )
