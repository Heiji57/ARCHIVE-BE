from datetime import datetime, timezone

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.github.domain.models.retrospective_push import RetrospectivePush
from app.github.domain.repositories.retrospective_push_repository import (
    IRetrospectivePushRepository,
)
from app.github.infrastructure.persistence.models.retrospective_push_model import (
    RetrospectivePushModel,
)
from app.shared.domain.utils.id import generate_id


class RetrospectivePushRepository(IRetrospectivePushRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, push: RetrospectivePush) -> RetrospectivePush:
        existing = await self._find_model(push.user_id, push.period_type, push.period_key)
        if existing is None:
            model = RetrospectivePushModel(
                id=push.id or generate_id("rp"),
                user_id=push.user_id,
                period_type=push.period_type,
                period_key=push.period_key,
                repository_id=push.repository_id,
                repository_full_name=push.repository_full_name,
                path=push.path,
                commit_sha=push.commit_sha,
                html_url=push.html_url,
                pushed_at=push.pushed_at,
                created_at=push.created_at or datetime.now(timezone.utc),
                updated_at=None,
            )
            self._session.add(model)
            await self._session.flush()
            return self._to_entity(model)

        existing.repository_id = push.repository_id
        existing.repository_full_name = push.repository_full_name
        existing.path = push.path
        existing.commit_sha = push.commit_sha
        existing.html_url = push.html_url
        existing.pushed_at = push.pushed_at
        existing.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return self._to_entity(existing)

    async def find_by_period(
        self, user_id: str, period_type: str, period_key: str
    ) -> RetrospectivePush | None:
        model = await self._find_model(user_id, period_type, period_key)
        return self._to_entity(model) if model else None

    async def find_many(
        self,
        user_id: str,
        keys: list[tuple[str, str]],
    ) -> list[RetrospectivePush]:
        if not keys:
            return []
        # 중복 제거
        unique_keys = list(set(keys))
        stmt = (
            select(RetrospectivePushModel)
            .where(
                RetrospectivePushModel.user_id == user_id,
                tuple_(
                    RetrospectivePushModel.period_type,
                    RetrospectivePushModel.period_key,
                ).in_(unique_keys),
            )
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def _find_model(
        self, user_id: str, period_type: str, period_key: str
    ) -> RetrospectivePushModel | None:
        result = await self._session.execute(
            select(RetrospectivePushModel).where(
                RetrospectivePushModel.user_id == user_id,
                RetrospectivePushModel.period_type == period_type,
                RetrospectivePushModel.period_key == period_key,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _to_entity(model: RetrospectivePushModel) -> RetrospectivePush:
        return RetrospectivePush(
            id=model.id,
            user_id=model.user_id,
            period_type=model.period_type,
            period_key=model.period_key,
            repository_id=model.repository_id,
            repository_full_name=model.repository_full_name,
            path=model.path,
            commit_sha=model.commit_sha,
            html_url=model.html_url,
            pushed_at=model.pushed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
