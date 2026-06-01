from pydantic import BaseModel

from app.user.domain.models.user import User


class TokenResponse(BaseModel):
    access_token: str


class UserResponse(BaseModel):
    id: str
    email: str

    @classmethod
    def from_entity(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=str(user.email),
        )
