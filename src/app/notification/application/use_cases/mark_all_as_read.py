from app.notification.domain.repositories.repository import INotificationRepository


class MarkAllAsReadUseCase:
    def __init__(self, repo: INotificationRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> None:
        await self._repo.mark_all_as_read(user_id)
