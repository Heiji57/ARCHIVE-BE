from app.notification.application.dtos.commands import CreateNotificationCommand
from app.notification.domain.models.notification import Notification
from app.notification.domain.repositories.repository import INotificationRepository


class CreateNotificationUseCase:
    def __init__(self, repo: INotificationRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: CreateNotificationCommand) -> Notification:
        notification = Notification.create(
            user_id=cmd.user_id,
            type=cmd.type,
            category=cmd.category,
            title=cmd.title,
            message=cmd.message,
        )
        return await self._repo.save(notification)
