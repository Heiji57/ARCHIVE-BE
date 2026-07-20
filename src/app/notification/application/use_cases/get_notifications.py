from app.notification.domain.models.notification import Notification
from app.notification.domain.repositories.repository import INotificationRepository


class GetNotificationsUseCase:
    def __init__(self, repo: INotificationRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str, unread_only: bool = False) -> list[Notification]:
        return await self._repo.find_by_user_id(user_id, unread_only=unread_only)
