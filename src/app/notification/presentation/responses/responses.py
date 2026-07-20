from datetime import datetime

from pydantic import BaseModel

from app.notification.domain.models.notification import Notification


class NotificationResponse(BaseModel):
    id: str
    type: str
    category: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

    @classmethod
    def from_entity(cls, n: Notification) -> "NotificationResponse":
        return cls(
            id=n.id,
            type=n.type.value,
            category=n.category.value,
            title=n.title,
            message=n.message,
            is_read=n.is_read,
            created_at=n.created_at,
        )
