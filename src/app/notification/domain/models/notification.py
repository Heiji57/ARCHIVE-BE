from dataclasses import dataclass
from datetime import datetime, timezone

from app.shared.domain.models.base import BaseEntity
from app.shared.domain.utils.id import generate_id


@dataclass(kw_only=True)
class Notification(BaseEntity):
    user_id: str
    message: str
    is_read: bool = False

    def mark_read(self) -> None:
        self.is_read = True

    @classmethod
    def create(cls, user_id: str, message: str) -> "Notification":
        now = datetime.now(timezone.utc)
        return cls(
            id=generate_id("notf"),
            user_id=user_id,
            message=message,
            is_read=False,
            created_at=now,
        )
