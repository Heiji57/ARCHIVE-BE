from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notification.domain.models.notification import Notification
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
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
        self, user_id: str, unread_only: bool = False, now: datetime | None = None
    ) -> list[Notification]:
        now = now or datetime.now(UTC)
        stmt = select(NotificationModel).where(
            NotificationModel.user_id == user_id,
            or_(
                NotificationModel.deliver_after.is_(None),
                NotificationModel.deliver_after <= now,
            ),
        )
        if unread_only:
            stmt = stmt.where(NotificationModel.is_read.is_(False))
        result = await self._session.execute(stmt.order_by(NotificationModel.created_at.desc()))
        return [self._to_entity(m) for m in result.scalars()]

    async def find_due_for_delivery(self, now: datetime, limit: int) -> list[Notification]:
        result = await self._session.execute(
            select(NotificationModel)
            .where(
                NotificationModel.deliver_after.is_not(None),
                NotificationModel.deliver_after <= now,
            )
            .order_by(NotificationModel.deliver_after, NotificationModel.id)
            .limit(limit)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def mark_delivered(self, ids: list[str]) -> None:
        if not ids:
            return
        await self._session.execute(
            update(NotificationModel)
            .where(NotificationModel.id.in_(ids))
            .values(deliver_after=None)
        )

    async def mark_as_read(self, id: str, user_id: str) -> None:
        await self._session.execute(
            update(NotificationModel)
            .where(NotificationModel.id == id, NotificationModel.user_id == user_id)
            .values(is_read=True)
        )

    async def mark_all_as_read(self, user_id: str) -> None:
        # 아직 보류 중(방해 금지)인 알림은 사용자가 본 적이 없으므로 건드리지 않는다.
        await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.is_read.is_(False),
                or_(
                    NotificationModel.deliver_after.is_(None),
                    NotificationModel.deliver_after <= datetime.now(UTC),
                ),
            )
            .values(is_read=True)
        )

    async def delete(self, id: str, user_id: str) -> None:
        await self._session.execute(
            sa_delete(NotificationModel)
            .where(NotificationModel.id == id, NotificationModel.user_id == user_id)
        )

    async def delete_read(self, user_id: str) -> None:
        await self._session.execute(
            sa_delete(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.is_read.is_(True))
        )

    async def delete_all(self, user_id: str) -> None:
        await self._session.execute(
            sa_delete(NotificationModel).where(NotificationModel.user_id == user_id)
        )

    def _to_model(self, entity: Notification) -> NotificationModel:
        return NotificationModel(
            id=entity.id,
            user_id=entity.user_id,
            type=entity.type.value,
            category=entity.category.value,
            title=entity.title,
            message=entity.message,
            is_read=entity.is_read,
            link=entity.link,
            deliver_after=entity.deliver_after,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: NotificationModel) -> Notification:
        return Notification(
            id=model.id,
            user_id=model.user_id,
            type=NotificationType(model.type),
            category=NotificationCategory(model.category),
            title=model.title,
            message=model.message,
            is_read=model.is_read,
            link=model.link,
            deliver_after=model.deliver_after,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
