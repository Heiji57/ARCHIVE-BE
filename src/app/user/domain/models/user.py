from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity
from app.user.domain.models.value_objects import Email


@dataclass(kw_only=True)
class User(BaseEntity):
    email: Email
    password_hash: str | None  # None — OAuth 전용 유저
    country: str
    region: str | None
    timezone: str

    def is_oauth_only(self) -> bool:
        return self.password_hash is None
