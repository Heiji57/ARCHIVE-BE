from app.notification.domain.repositories.repository import INotificationRepository


class DeleteNotificationUseCase:
    def __init__(self, repo: INotificationRepository) -> None:
        self._repo = repo

    async def execute(self, notification_id: str, user_id: str) -> None:
        await self._repo.delete(notification_id, user_id)
