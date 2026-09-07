from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.topic.domain.models.topic import Topic, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.domain.repositories.repository import ITopicDigestRepository, ITopicRepository
from app.topic.infrastructure.persistence.models.topic_model import TopicDigestModel, TopicModel


class TopicRepository(ITopicRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, topic: Topic) -> Topic:
        model = self._to_model(topic)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, topic_id: str, user_id: str) -> Topic | None:
        result = await self._session.execute(
            select(TopicModel).where(
                TopicModel.id == topic_id,
                TopicModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_all_by_user(self, user_id: str) -> list[Topic]:
        result = await self._session.execute(
            select(TopicModel)
            .where(TopicModel.user_id == user_id)
            .order_by(TopicModel.created_at.asc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, topic_id: str, user_id: str) -> None:
        result = await self._session.execute(
            select(TopicModel).where(
                TopicModel.id == topic_id,
                TopicModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def exists_by_name(self, user_id: str, name: str) -> bool:
        result = await self._session.execute(
            select(func.count()).select_from(TopicModel).where(
                TopicModel.user_id == user_id,
                TopicModel.name == name,
            )
        )
        return result.scalar_one() > 0

    async def count_by_user(self, user_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(TopicModel).where(
                TopicModel.user_id == user_id
            )
        )
        return result.scalar_one()

    @staticmethod
    def _to_model(topic: Topic) -> TopicModel:
        return TopicModel(
            id=topic.id,
            user_id=topic.user_id,
            name=topic.name,
            description=topic.description,
            created_at=topic.created_at,
            updated_at=topic.updated_at,
        )

    @staticmethod
    def _to_entity(model: TopicModel) -> Topic:
        return Topic(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            description=model.description,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class TopicDigestRepository(ITopicDigestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, digest: TopicDigest) -> TopicDigest:
        model = self._to_model(digest)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_topic(self, topic_id: str, user_id: str) -> TopicDigest | None:
        result = await self._session.execute(
            select(TopicDigestModel).where(
                TopicDigestModel.topic_id == topic_id,
                TopicDigestModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_id(self, digest_id: str, user_id: str) -> TopicDigest | None:
        result = await self._session.execute(
            select(TopicDigestModel).where(
                TopicDigestModel.id == digest_id,
                TopicDigestModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update_status(
        self,
        digest_id: str,
        status: DigestStatus,
        content: str | None = None,
    ) -> None:
        result = await self._session.execute(
            select(TopicDigestModel).where(TopicDigestModel.id == digest_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.status = status.value
            if content is not None:
                model.content = content
            model.updated_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def update_watermark(self, digest_id: str, watermark_date_key: str) -> None:
        result = await self._session.execute(
            select(TopicDigestModel).where(TopicDigestModel.id == digest_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.watermark_date_key = watermark_date_key
            model.updated_at = datetime.now(timezone.utc)
            await self._session.flush()

    @staticmethod
    def _to_model(digest: TopicDigest) -> TopicDigestModel:
        return TopicDigestModel(
            id=digest.id,
            topic_id=digest.topic_id,
            user_id=digest.user_id,
            status=digest.status.value,
            content=digest.content,
            watermark_date_key=digest.watermark_date_key,
            created_at=digest.created_at,
            updated_at=digest.updated_at,
        )

    @staticmethod
    def _to_entity(model: TopicDigestModel) -> TopicDigest:
        return TopicDigest(
            id=model.id,
            topic_id=model.topic_id,
            user_id=model.user_id,
            status=DigestStatus(model.status),
            content=model.content,
            watermark_date_key=model.watermark_date_key,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
