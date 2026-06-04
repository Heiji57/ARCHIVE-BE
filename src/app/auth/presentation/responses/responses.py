from pydantic import BaseModel, Field

from app.user.domain.models.user import User


class TokenResponse(BaseModel):
    access_token: str = Field(serialization_alias="accessToken")

    model_config = {"populate_by_name": True}


class UserResponse(BaseModel):
    id: str
    email: str
    country: str
    region: str | None = None
    timezone: str

    @classmethod
    def from_entity(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=str(user.email),
            country=user.country,
            region=user.region,
            timezone=user.timezone,
        )


class OAuthLinkInitResponse(BaseModel):
    authorize_url: str = Field(serialization_alias="authorizeUrl")

    model_config = {"populate_by_name": True}
