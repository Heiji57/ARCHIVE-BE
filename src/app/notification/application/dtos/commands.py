from dataclasses import dataclass

from app.notification.domain.models.value_objects import NotificationCategory, NotificationType


@dataclass(frozen=True)
class CreateNotificationCommand:
    user_id: str
    type: NotificationType
    category: NotificationCategory
    title: str
    message: str
