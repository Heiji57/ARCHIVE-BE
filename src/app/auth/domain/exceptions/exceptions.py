from app.shared.domain.exceptions.base import BaseAppException


class AuthTokenExpiredException(BaseAppException):
    code = "AUTH_TOKEN_EXPIRED"


class AuthTokenInvalidException(BaseAppException):
    code = "AUTH_TOKEN_INVALID"


class AuthInvalidCredentialsException(BaseAppException):
    code = "AUTH_INVALID_CREDENTIALS"


class Auth2FACodeInvalidException(BaseAppException):
    code = "AUTH_2FA_CODE_INVALID"


class OAuthStateInvalidException(BaseAppException):
    code = "AUTH_OAUTH_STATE_INVALID"


class RefreshTokenInvalidException(BaseAppException):
    code = "AUTH_REFRESH_TOKEN_INVALID"


class RefreshTokenRevokedException(BaseAppException):
    code = "AUTH_REFRESH_TOKEN_REVOKED"


class RefreshTokenReuseDetectedException(BaseAppException):
    """폐기된 refresh token이 재사용됨 — 탈취 의심. 해당 사용자의 모든 세션이 즉시 폐기된다."""
    code = "AUTH_REFRESH_TOKEN_REUSE_DETECTED"


class SessionNotFoundException(BaseAppException):
    """sessionId에 해당하는 활성 세션이 없음 (이미 폐기되었거나 존재한 적 없음)."""
    code = "AUTH_SESSION_NOT_FOUND"


class EmailNotVerifiedException(BaseAppException):
    code = "AUTH_EMAIL_NOT_VERIFIED"


class OnboardingTokenInvalidException(BaseAppException):
    code = "AUTH_ONBOARDING_TOKEN_INVALID"


class OnboardingTokenExpiredException(BaseAppException):
    code = "AUTH_ONBOARDING_TOKEN_EXPIRED"


class CountryInvalidException(BaseAppException):
    """ISO 3166-1 alpha-2 미등록 국가, 또는 timezone 데이터가 없는 국가."""
    code = "AUTH_COUNTRY_INVALID"


class CountryTimezoneRequiredException(BaseAppException):
    """다중 timezone 국가(예: US, RU, BR)는 IANA timezone 명시 필수."""
    code = "AUTH_COUNTRY_TIMEZONE_REQUIRED"


class TimezoneInvalidException(BaseAppException):
    """주어진 timezone 이 IANA tz 가 아니거나 해당 국가의 옵션 밖."""
    code = "AUTH_TIMEZONE_INVALID"


class OAuthAccountAlreadyLinkedException(BaseAppException):
    """OAuth 계정이 이미 다른 사용자에 연결됨."""
    code = "AUTH_OAUTH_ACCOUNT_ALREADY_LINKED"


class OAuthProviderAlreadyLinkedException(BaseAppException):
    """이미 같은 provider에 다른 계정으로 연결되어 있음 (provider당 1개 정책)."""
    code = "AUTH_OAUTH_PROVIDER_ALREADY_LINKED"


class PasswordResetTokenInvalidException(BaseAppException):
    code = "AUTH_PASSWORD_RESET_TOKEN_INVALID"


class PasswordResetTokenExpiredException(BaseAppException):
    code = "AUTH_PASSWORD_RESET_TOKEN_EXPIRED"


class PasswordResetNotAllowedException(BaseAppException):
    """OAuth 전용 사용자(비밀번호 없음)는 재설정 불가."""
    code = "AUTH_PASSWORD_RESET_NOT_ALLOWED"
