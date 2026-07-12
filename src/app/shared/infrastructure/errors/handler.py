from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth.domain.exceptions.exceptions import (
    Auth2FACodeInvalidException,
    AuthInvalidCredentialsException,
    AuthTokenExpiredException,
    AuthTokenInvalidException,
    CountryInvalidException,
    CountryTimezoneRequiredException,
    EmailNotVerifiedException,
    LoginRateLimitExceededException,
    OAuthAccountAlreadyLinkedException,
    OAuthProviderAlreadyLinkedException,
    OAuthStateInvalidException,
    OnboardingTokenExpiredException,
    OnboardingTokenInvalidException,
    PasswordResetNotAllowedException,
    PasswordResetTokenExpiredException,
    PasswordResetTokenInvalidException,
    RefreshTokenInvalidException,
    RefreshTokenReuseDetectedException,
    RefreshTokenRevokedException,
    SessionNotFoundException,
    TimezoneInvalidException,
)
from app.github.domain.exceptions.exceptions import (
    DeveloperAccountRequiredException,
    GitHubApiUnavailableException,
    GitHubConnectionNotFoundException,
    GitHubPushFailedException,
    GitHubPushTargetNotSetException,
    GitHubRateLimitedException,
    GitHubRepositoryAlreadyLinkedException,
    GitHubRepositoryNotFoundException,
    GitHubRepositoryNotLinkedException,
    GitHubTokenInvalidException,
)
from app.google_calendar.domain.exceptions.exceptions import (
    CalendarApiUnavailableException,
    CalendarNotConnectedException,
    CalendarReauthRequiredException,
    CalendarStateInvalidException,
)
from app.notification.domain.exceptions.exceptions import NotificationNotFoundException
from app.retrospective.domain.exceptions.exceptions import (
    FolderCircularReferenceException,
    FolderNameDuplicatedException,
    FolderNotFoundException,
    JournalEntryAlreadyExistsException,
    JournalEntryNotFoundException,
    RetroSummaryNotFoundException,
    RetroTemplateDefaultNotDeletableException,
    RetroTemplateNameDuplicatedException,
    RetroTemplateNotFoundException,
    RetroTemplateTypeMismatchException,
    SummaryAlreadyInProgressException,
    SummaryInvalidStateException,
    SummaryRateLimitExceededException,
    SummaryReadinessUnsupportedException,
    SummaryTemplateInUseException,
    SummaryTemplateLimitReachedException,
    SummaryTemplateNameDuplicatedException,
    SummaryTemplateNotFoundException,
)
from app.shared.domain.exceptions.base import BaseAppException
from app.todo.domain.exceptions.exceptions import (
    TodoAlreadyCompletedException,
    TodoAlreadyInProgressException,
    TodoNotFoundException,
)
from app.user.domain.exceptions.exceptions import (
    InvalidEmailException,
    UserEmailDuplicatedException,
    UserNotFoundException,
)

_STATUS_MAP: dict[str, int] = {
    # 403
    DeveloperAccountRequiredException.code: 403,
    # 400
    OAuthStateInvalidException.code: 400,
    SummaryInvalidStateException.code: 400,
    EmailNotVerifiedException.code: 400,
    InvalidEmailException.code: 400,
    GitHubConnectionNotFoundException.code: 400,
    GitHubPushTargetNotSetException.code: 400,
    GitHubRepositoryNotLinkedException.code: 400,
    PasswordResetNotAllowedException.code: 400,
    CalendarNotConnectedException.code: 400,
    CalendarStateInvalidException.code: 400,
    # 401
    AuthTokenInvalidException.code: 401,
    AuthTokenExpiredException.code: 401,
    AuthInvalidCredentialsException.code: 401,
    RefreshTokenInvalidException.code: 401,
    RefreshTokenRevokedException.code: 401,
    RefreshTokenReuseDetectedException.code: 401,
    Auth2FACodeInvalidException.code: 401,
    GitHubTokenInvalidException.code: 401,
    CalendarReauthRequiredException.code: 401,
    OnboardingTokenInvalidException.code: 401,
    OnboardingTokenExpiredException.code: 401,
    PasswordResetTokenInvalidException.code: 401,
    PasswordResetTokenExpiredException.code: 401,
    # 400
    RetroTemplateDefaultNotDeletableException.code: 400,
    # 404
    UserNotFoundException.code: 404,
    TodoNotFoundException.code: 404,
    JournalEntryNotFoundException.code: 404,
    RetroSummaryNotFoundException.code: 404,
    NotificationNotFoundException.code: 404,
    GitHubRepositoryNotFoundException.code: 404,
    SessionNotFoundException.code: 404,
    SummaryTemplateNotFoundException.code: 404,
    RetroTemplateNotFoundException.code: 404,
    FolderNotFoundException.code: 404,
    # 409
    UserEmailDuplicatedException.code: 409,
    TodoAlreadyCompletedException.code: 409,
    TodoAlreadyInProgressException.code: 409,
    JournalEntryAlreadyExistsException.code: 409,
    SummaryAlreadyInProgressException.code: 409,
    GitHubRepositoryAlreadyLinkedException.code: 409,
    OAuthAccountAlreadyLinkedException.code: 409,
    OAuthProviderAlreadyLinkedException.code: 409,
    SummaryTemplateNameDuplicatedException.code: 409,
    SummaryTemplateLimitReachedException.code: 409,
    SummaryTemplateInUseException.code: 409,
    RetroTemplateNameDuplicatedException.code: 409,
    FolderNameDuplicatedException.code: 409,
    # 422
    RetroTemplateTypeMismatchException.code: 422,
    CountryInvalidException.code: 422,
    CountryTimezoneRequiredException.code: 422,
    TimezoneInvalidException.code: 422,
    SummaryReadinessUnsupportedException.code: 422,
    FolderCircularReferenceException.code: 422,
    # 429
    GitHubRateLimitedException.code: 429,
    SummaryRateLimitExceededException.code: 429,
    LoginRateLimitExceededException.code: 429,
    # 502
    GitHubPushFailedException.code: 502,
    # 503
    GitHubApiUnavailableException.code: 503,
    CalendarApiUnavailableException.code: 503,
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
