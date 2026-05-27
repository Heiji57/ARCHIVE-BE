from dataclasses import dataclass


@dataclass(frozen=True)
class SendEmailVerificationCommand:
    email: str


@dataclass(frozen=True)
class VerifyEmailCodeCommand:
    email: str
    code: str


@dataclass(frozen=True)
class RegisterCommand:
    email: str
    password: str
    device_info: str | None = None


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str
    device_info: str | None = None
