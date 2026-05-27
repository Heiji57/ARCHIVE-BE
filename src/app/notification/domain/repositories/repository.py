from abc import ABC, abstractmethod

from app.notification.domain.models.notification import Notification


class INotificationRepository(ABC):
    @abstractmethod
    async def save(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def find_by_user_id(
        self, user_id: str, unread_only: bool = False
    ) -> list[Notification]: ...

    @abstractmethod
    async def mark_as_read(self, id: str, user_id: str) -> None: ...

    @abstractmethod
    async def mark_all_as_read(self, user_id: str) -> None: ...
