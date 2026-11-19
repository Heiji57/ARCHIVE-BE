from abc import ABC, abstractmethod
from datetime import datetime

from app.notification.domain.models.notification import Notification


class INotificationRepository(ABC):
    @abstractmethod
    async def save(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def find_by_user_id(
        self, user_id: str, unread_only: bool = False, now: datetime | None = None
    ) -> list[Notification]:
        """목록 — 방해 금지로 보류 중(deliver_after > now)인 알림은 뺀다."""
        ...

    @abstractmethod
    async def find_due_for_delivery(self, now: datetime, limit: int) -> list[Notification]:
        """보류 시각이 지난 알림(deliver_after <= now). 오래된 순."""
        ...

    @abstractmethod
    async def mark_delivered(self, ids: list[str]) -> None:
        """보류 해제(deliver_after = NULL) — SSE 로 보낸 뒤 호출."""
        ...

    @abstractmethod
    async def mark_as_read(self, id: str, user_id: str) -> None: ...

    @abstractmethod
    async def mark_all_as_read(self, user_id: str) -> None: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...

    @abstractmethod
    async def delete_read(self, user_id: str) -> None: ...

    @abstractmethod
    async def delete_all(self, user_id: str) -> None: ...
