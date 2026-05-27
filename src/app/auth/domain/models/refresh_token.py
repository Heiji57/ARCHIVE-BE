from dataclasses import dataclass
from datetime import datetime, timezone

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class RefreshToken(BaseEntity):
    user_id: str
    token_hash: str
    device_info: str | None
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None

    def is_valid(self) -> bool:
        return (
            self.revoked_at is None
            and self.expires_at > datetime.now(timezone.utc)
        )

    def revoke(self) -> None:
        self.revoked_at = datetime.now(timezone.utc)

    def record_usage(self) -> None:
        self.last_used_at = datetime.now(timezone.utc)
