from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notification.domain.models.notification import Notification
from app.notification.domain.repositories.repository import INotificationRepository
from app.notification.infrastructure.persistence.models.notification_model import NotificationModel


class NotificationRepository(INotificationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, notification: Notification) -> Notification:
        model = self._to_model(notification)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_user_id(
        self, user_id: str, unread_only: bool = False
    ) -> list[Notification]:
        stmt = select(NotificationModel).where(NotificationModel.user_id == user_id)
        if unread_only:
            stmt = stmt.where(NotificationModel.is_read.is_(False))
        result = await self._session.execute(stmt.order_by(NotificationModel.created_at.desc()))
        return [self._to_entity(m) for m in result.scalars()]

    async def mark_as_read(self, id: str, user_id: str) -> None:
        await self._session.execute(
            update(NotificationModel)
            .where(NotificationModel.id == id, NotificationModel.user_id == user_id)
            .values(is_read=True)
        )

    async def mark_all_as_read(self, user_id: str) -> None:
        await self._session.execute(
            update(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.is_read.is_(False))
            .values(is_read=True)
        )

    def _to_model(self, entity: Notification) -> NotificationModel:
        return NotificationModel(
            id=entity.id,
            user_id=entity.user_id,
            message=entity.message,
            is_read=entity.is_read,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: NotificationModel) -> Notification:
        return Notification(
            id=model.id,
            user_id=model.user_id,
            message=model.message,
            is_read=model.is_read,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
