from dataclasses import dataclass, field

from app.shared.domain.models.base import BaseEntity
from app.user.domain.models.value_objects import Email


@dataclass(kw_only=True)
class User(BaseEntity):
    email: Email
    password_hash: str | None  # None — OAuth 전용 유저
    country: str
    region: str | None
    timezone: str
    account_type: str = field(default="user")  # "developer" | "user"

    def is_oauth_only(self) -> bool:
        return self.password_hash is None

    def is_developer(self) -> bool:
        return self.account_type == "developer"
