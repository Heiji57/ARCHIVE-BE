from pydantic import BaseModel, Field

from app.auth.infrastructure.storage.avatar_storage import avatar_url
from app.shared.infrastructure.config.settings import get_settings
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
    display_name: str | None = Field(default=None, serialization_alias="displayName")
    avatar_url: str | None = Field(default=None, serialization_alias="avatarUrl")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=str(user.email),
            country=user.country,
            region=user.region,
            timezone=user.timezone,
            display_name=user.display_name,
            avatar_url=avatar_url(get_settings().auth.avatar_public_path, user.avatar_key),
        )


class UpdateProfileResponse(BaseModel):
    user: UserResponse

    model_config = {"populate_by_name": True}


class OAuthLinkInitResponse(BaseModel):
    authorize_url: str = Field(serialization_alias="authorizeUrl")

    model_config = {"populate_by_name": True}
