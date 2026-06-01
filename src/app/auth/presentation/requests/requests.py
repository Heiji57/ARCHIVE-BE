import re

from pydantic import BaseModel, EmailStr, field_validator

_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")


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
    password_confirm: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    def validate_passwords_match(self) -> None:
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match.")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
