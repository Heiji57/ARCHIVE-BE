import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_IANA_TZ_RE = re.compile(r"^[A-Za-z]+(?:[/_-][A-Za-z0-9_+-]+)+$")


def _normalize_country(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Country must be a string.")
    normalized = v.strip().upper()
    if not _COUNTRY_RE.fullmatch(normalized):
        raise ValueError("Country must be an ISO 3166-1 alpha-2 code.")
    return normalized


def _normalize_optional_timezone(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise ValueError("Timezone must be a string.")
    normalized = v.strip()
    if not _IANA_TZ_RE.fullmatch(normalized):
        raise ValueError(
            "Timezone must be an IANA identifier like 'Asia/Seoul' or 'America/Los_Angeles'."
        )
    return normalized


class SendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

    @field_validator("code", mode="before")
    @classmethod
    def code_must_be_valid(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Code must be a string.")
        normalized = v.strip().upper()
        if not _CODE_RE.fullmatch(normalized):
            raise ValueError("Code must be 6 characters of uppercase letters or digits.")
        return normalized


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    password_confirm: str = Field(alias="passwordConfirm")
    country: str
    timezone: str | None = None  # 다중 tz 국가일 때만 필수

    model_config = {"populate_by_name": True}

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("country", mode="before")
    @classmethod
    def country_format(cls, v: str) -> str:
        return _normalize_country(v)

    @field_validator("timezone", mode="before")
    @classmethod
    def timezone_format(cls, v: str | None) -> str | None:
        return _normalize_optional_timezone(v)

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterRequest":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    account_type: str | None = None

    @field_validator("account_type", mode="before")
    @classmethod
    def account_type_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("developer", "user"):
            raise ValueError("account_type must be 'developer' or 'user'")
        return v


class OnboardingCompleteRequest(BaseModel):
    country: str
    timezone: str | None = None

    @field_validator("country", mode="before")
    @classmethod
    def country_format(cls, v: str) -> str:
        return _normalize_country(v)

    @field_validator("timezone", mode="before")
    @classmethod
    def timezone_format(cls, v: str | None) -> str | None:
        return _normalize_optional_timezone(v)


class UpdateCountryRequest(BaseModel):
    country: str
    timezone: str | None = None

    @field_validator("country", mode="before")
    @classmethod
    def country_format(cls, v: str) -> str:
        return _normalize_country(v)

    @field_validator("timezone", mode="before")
    @classmethod
    def timezone_format(cls, v: str | None) -> str | None:
        return _normalize_optional_timezone(v)


class UpdateTimezoneRequest(BaseModel):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def timezone_format(cls, v: str) -> str:
        if not isinstance(v, str) or "/" not in v:
            raise ValueError("Timezone must be an IANA identifier like 'Asia/Seoul'.")
        return v.strip()


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=120)
    new_password: str = Field(alias="newPassword")
    new_password_confirm: str = Field(alias="newPasswordConfirm")

    model_config = {"populate_by_name": True}

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.new_password_confirm:
            raise ValueError("Passwords do not match.")
        return self
