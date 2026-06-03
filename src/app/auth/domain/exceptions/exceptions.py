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


class EmailNotVerifiedException(BaseAppException):
    code = "AUTH_EMAIL_NOT_VERIFIED"


class OnboardingTokenInvalidException(BaseAppException):
    code = "AUTH_ONBOARDING_TOKEN_INVALID"


class OnboardingTokenExpiredException(BaseAppException):
    code = "AUTH_ONBOARDING_TOKEN_EXPIRED"


class CountryInvalidException(BaseAppException):
    code = "AUTH_COUNTRY_INVALID"


class CountryRegionRequiredException(BaseAppException):
    code = "AUTH_COUNTRY_REGION_REQUIRED"


class TimezoneInvalidException(BaseAppException):
    code = "AUTH_TIMEZONE_INVALID"
