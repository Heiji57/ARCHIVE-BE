import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_REGION_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")


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
    region: str | None = None

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
        if not isinstance(v, str):
            raise ValueError("Country must be a string.")
        normalized = v.strip().upper()
        if not _COUNTRY_RE.fullmatch(normalized):
            raise ValueError("Country must be an ISO 3166-1 alpha-2 code.")
        return normalized

    @field_validator("region", mode="before")
    @classmethod
    def region_format(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("Region must be a string.")
        normalized = v.strip().upper()
        if not _REGION_RE.fullmatch(normalized):
            raise ValueError("Region must be an ISO 3166-2 code like 'US-CA'.")
        return normalized

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


class OnboardingCompleteRequest(BaseModel):
    country: str
    region: str | None = None

    @field_validator("country", mode="before")
    @classmethod
    def country_format(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Country must be a string.")
        normalized = v.strip().upper()
        if not _COUNTRY_RE.fullmatch(normalized):
            raise ValueError("Country must be an ISO 3166-1 alpha-2 code.")
        return normalized

    @field_validator("region", mode="before")
    @classmethod
    def region_format(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("Region must be a string.")
        normalized = v.strip().upper()
        if not _REGION_RE.fullmatch(normalized):
            raise ValueError("Region must be an ISO 3166-2 code like 'US-CA'.")
        return normalized


class UpdateCountryRequest(BaseModel):
    country: str
    region: str | None = None

    @field_validator("country", mode="before")
    @classmethod
    def country_format(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Country must be a string.")
        normalized = v.strip().upper()
        if not _COUNTRY_RE.fullmatch(normalized):
            raise ValueError("Country must be an ISO 3166-1 alpha-2 code.")
        return normalized

    @field_validator("region", mode="before")
    @classmethod
    def region_format(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("Region must be a string.")
        normalized = v.strip().upper()
        if not _REGION_RE.fullmatch(normalized):
            raise ValueError("Region must be an ISO 3166-2 code like 'US-CA'.")
        return normalized


class UpdateTimezoneRequest(BaseModel):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def timezone_format(cls, v: str) -> str:
        if not isinstance(v, str) or "/" not in v:
            raise ValueError("Timezone must be an IANA identifier like 'Asia/Seoul'.")
        return v.strip()
