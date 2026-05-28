from pydantic import BaseModel

from app.user.domain.models.user import User


class TokenResponse(BaseModel):
    access_token: str


class PreAuthTokenResponse(BaseModel):
    pre_auth_token: str
    requires_2fa: bool = True


class UserResponse(BaseModel):
    id: str
    email: str
    totp_enabled: bool

    @classmethod
    def from_entity(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=str(user.email),
            totp_enabled=user.totp_enabled,
        )
