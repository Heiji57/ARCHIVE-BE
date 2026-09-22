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


class LoginRateLimitExceededException(BaseAppException):
    """로그인 실패 누적으로 일시 차단됨 — brute-force 방어 (email+IP 고정 윈도우)."""
    code = "AUTH_LOGIN_RATE_LIMITED"


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


# ── 이메일 인증 (v1 에선 전부 AUTH_TOKEN_INVALID 로 매핑 — errors/handler.py) ──

class EmailCodeInvalidException(BaseAppException):
    """인증 코드 불일치. 남은 시도 횟수 안에서 재입력 가능."""
    code = "AUTH_EMAIL_CODE_INVALID"


class EmailCodeExpiredException(BaseAppException):
    """인증 코드 만료 또는 발급 이력 없음. 새 코드 요청 필요."""
    code = "AUTH_EMAIL_CODE_EXPIRED"


class EmailCodeAttemptsExceededException(BaseAppException):
    """인증 코드 오입력 한도 초과. 코드는 폐기되며 새 코드 요청 필요."""
    code = "AUTH_EMAIL_CODE_ATTEMPTS_EXCEEDED"


class EmailSendCooldownException(BaseAppException):
    """인증 코드 재발송 쿨다운 중."""
    code = "AUTH_EMAIL_SEND_COOLDOWN"


# ── OAuth provider 연동 ────────────────────────────────────────────────────────

class OAuthCodeInvalidException(BaseAppException):
    """provider 가 authorization code 를 거부 (만료·재사용). state 위조와 구분한다."""
    code = "AUTH_OAUTH_CODE_INVALID"


class OAuthEmailNotVerifiedException(BaseAppException):
    """provider 계정에 인증된(primary) 이메일이 없음."""
    code = "AUTH_OAUTH_EMAIL_NOT_VERIFIED"


class OAuthProviderUnavailableException(BaseAppException):
    """provider 네트워크 오류·타임아웃·5xx·429 — 일시 장애, 재시도 가능."""
    code = "AUTH_OAUTH_PROVIDER_UNAVAILABLE"


class OAuthProviderResponseInvalidException(BaseAppException):
    """provider 응답이 예상 형식이 아니거나 우리 요청을 거부 (client 설정 오류 등)."""
    code = "AUTH_OAUTH_PROVIDER_RESPONSE_INVALID"
