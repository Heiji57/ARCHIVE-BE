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
    EmailCodeAttemptsExceededException,
    EmailCodeExpiredException,
    EmailCodeInvalidException,
    EmailNotVerifiedException,
    EmailSendCooldownException,
    LoginRateLimitExceededException,
    OAuthAccountAlreadyLinkedException,
    OAuthCodeInvalidException,
    OAuthEmailNotVerifiedException,
    OAuthProviderAlreadyLinkedException,
    OAuthProviderResponseInvalidException,
    OAuthProviderUnavailableException,
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
    GitHubPermissionDeniedException,
    GitHubPushFailedException,
    GitHubPushTargetNotSetException,
    GitHubRateLimitedException,
    GitHubRepositoryAlreadyLinkedException,
    GitHubRepositoryNotFoundException,
    GitHubRepositoryNotLinkedException,
    GitHubResponseInvalidException,
    GitHubTokenInvalidException,
)
from app.google_calendar.domain.exceptions.exceptions import (
    CalendarApiUnavailableException,
    CalendarNotConnectedException,
    CalendarRateLimitedException,
    CalendarReauthRequiredException,
    CalendarResponseInvalidException,
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
from app.shared.domain.exceptions.external import (
    AIEmptyResponseException,
    AIQuotaExceededException,
    AIRequestRejectedException,
    AIServiceException,
    AIServiceUnavailableException,
    CacheUnavailableException,
    EmailDeliveryFailedException,
)
from app.topic.domain.exceptions.exceptions import (
    DigestAlreadyInProgressException,
    DigestNotFoundException,
    TopicLimitReachedException,
    TopicNameDuplicatedException,
    TopicNotFoundException,
)
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
    # ── Topic ────────────────────────────────────────────────────────────────
    # 404
    TopicNotFoundException.code: 404,
    DigestNotFoundException.code: 404,
    # 409
    TopicNameDuplicatedException.code: 409,
    TopicLimitReachedException.code: 409,
    DigestAlreadyInProgressException.code: 409,
    # 429
    GitHubRateLimitedException.code: 429,
    SummaryRateLimitExceededException.code: 429,
    LoginRateLimitExceededException.code: 429,
    # 502
    GitHubPushFailedException.code: 502,
    # 503
    GitHubApiUnavailableException.code: 503,
    CalendarApiUnavailableException.code: 503,
    # ── Auth 세분화 (v2) ─────────────────────────────────────────────────────
    EmailCodeInvalidException.code: 400,
    EmailCodeExpiredException.code: 400,
    EmailCodeAttemptsExceededException.code: 429,
    EmailSendCooldownException.code: 429,
    OAuthCodeInvalidException.code: 400,
    OAuthEmailNotVerifiedException.code: 400,
    OAuthProviderUnavailableException.code: 503,
    OAuthProviderResponseInvalidException.code: 502,
    # ── GitHub 세분화 ────────────────────────────────────────────────────────
    GitHubPermissionDeniedException.code: 403,
    GitHubResponseInvalidException.code: 502,
    # ── Google Calendar 세분화 ───────────────────────────────────────────────
    CalendarRateLimitedException.code: 429,
    CalendarResponseInvalidException.code: 502,
    # ── 외부 연동 공통 (shared/domain/exceptions/external.py) ────────────────
    EmailDeliveryFailedException.code: 503,
    CacheUnavailableException.code: 503,
    # AI 예외는 주로 워커에서만 발생 — HTTP 로 새는 경로(토픽 매칭 등)는 degrade 처리하므로
    # api.yaml 엔드포인트 계약에는 없다. 새어 나가더라도 올바른 상태로 응답하도록 등록만 한다.
    AIServiceException.code: 502,
    AIServiceUnavailableException.code: 503,
    AIQuotaExceededException.code: 503,  # 우리 쪽 쿼터 소진 — 클라이언트 rate limit(429) 아님
    AIRequestRejectedException.code: 502,
    AIEmptyResponseException.code: 502,
}

# v1 하위호환 — 세분화 이전에 같은 상황에서 내보내던 코드. v1 경로(와 v1 으로 시작한 OAuth
# 흐름)에서는 새 코드를 이 값으로 되돌린다. 이전에 KeyError 등으로 500 이 나던 상황은
# INTERNAL_ERROR. 새 예외를 추가할 때 v1 계약이 바뀌면 여기에 등록한다.
_V1_LEGACY_CODES: dict[str, str] = {
    EmailCodeInvalidException.code: AuthTokenInvalidException.code,
    EmailCodeExpiredException.code: AuthTokenInvalidException.code,
    EmailCodeAttemptsExceededException.code: AuthTokenInvalidException.code,
    EmailSendCooldownException.code: AuthTokenInvalidException.code,
    OAuthCodeInvalidException.code: OAuthStateInvalidException.code,
    OAuthEmailNotVerifiedException.code: OAuthStateInvalidException.code,
    OAuthProviderUnavailableException.code: BaseAppException.code,
    OAuthProviderResponseInvalidException.code: BaseAppException.code,
    EmailDeliveryFailedException.code: BaseAppException.code,
    CacheUnavailableException.code: BaseAppException.code,
    GitHubPermissionDeniedException.code: GitHubApiUnavailableException.code,
    GitHubResponseInvalidException.code: BaseAppException.code,
    # Calendar 두 예외는 CalendarApiUnavailable 하위 — v1 에선 그 코드로 보였다.
    CalendarRateLimitedException.code: CalendarApiUnavailableException.code,
    CalendarResponseInvalidException.code: CalendarApiUnavailableException.code,
    AIServiceException.code: BaseAppException.code,
    AIServiceUnavailableException.code: BaseAppException.code,
    AIQuotaExceededException.code: BaseAppException.code,
    AIRequestRejectedException.code: BaseAppException.code,
    AIEmptyResponseException.code: BaseAppException.code,
}


def api_version_of(path: str) -> str:
    """요청 경로의 API 버전. v2 는 일부 엔드포인트에만 존재하므로 그 외는 전부 v1."""
    return "v2" if path.startswith("/api/v2/") else "v1"


def resolve_code(code: str, api_version: str) -> str:
    if api_version == "v1":
        return _V1_LEGACY_CODES.get(code, code)
    return code


def to_http_response(exc: BaseAppException, api_version: str = "v1") -> JSONResponse:
    code = resolve_code(exc.code, api_version)
    status_code = _STATUS_MAP.get(code, 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "code": code,
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
