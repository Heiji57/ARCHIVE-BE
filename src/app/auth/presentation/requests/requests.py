from pydantic import BaseModel, EmailStr, field_validator


class SendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

    @field_validator("code")
    @classmethod
    def code_must_be_six_digits(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Code must be a 6-digit number.")
        return v


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

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info: object) -> str:
        from pydantic import model_validator  # noqa: F401
        return v

    def validate_passwords_match(self) -> None:
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match.")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
