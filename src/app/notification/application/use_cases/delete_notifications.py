from app.notification.domain.repositories.repository import INotificationRepository


class DeleteNotificationsUseCase:
    def __init__(self, repo: INotificationRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str, read_only: bool = False) -> None:
        if read_only:
            await self._repo.delete_read(user_id)
        else:
            await self._repo.delete_all(user_id)
