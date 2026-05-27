from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity
from app.user.domain.exceptions.exceptions import (
    TotpAlreadyEnabledException,
    TotpNotEnabledException,
)
from app.user.domain.models.value_objects import Email


@dataclass(kw_only=True)
class User(BaseEntity):
    email: Email
    password_hash: str | None  # None — OAuth 전용 유저
    totp_enabled: bool
    totp_secret: str | None

    def enable_totp(self, secret: str) -> None:
        if self.totp_enabled:
            raise TotpAlreadyEnabledException()
        self.totp_secret = secret
        self.totp_enabled = True

    def disable_totp(self) -> None:
        if not self.totp_enabled:
            raise TotpNotEnabledException()
        self.totp_secret = None
        self.totp_enabled = False

    def is_oauth_only(self) -> bool:
        return self.password_hash is None
