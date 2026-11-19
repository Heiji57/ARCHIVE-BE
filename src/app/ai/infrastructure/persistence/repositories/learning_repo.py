from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.domain.models.learning import BehaviorEvent, BehaviorModel
from app.ai.domain.repositories.repository import IBehaviorRepository
from app.ai.infrastructure.persistence.models.learning_model import (
    AiBehaviorEventModel,
    AiUserModelModel,
)
from app.shared.domain.utils.id import generate_id


class BehaviorRepository(IBehaviorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_event(
        self, user_id: str, event: BehaviorEvent, mark_stale: bool = True
    ) -> None:
        self._session.add(
            AiBehaviorEventModel(
                id=generate_id("bev"),
                user_id=user_id,
                type=event.type,
                todo_id=event.todo_id,
                data=event.data,
                created_at=event.created_at,
            )
        )
        if mark_stale:
            await self._session.execute(
                update(AiUserModelModel)
                .where(AiUserModelModel.user_id == user_id)
                .values(stale=True)
            )

    async def list_events_since(self, user_id: str, since: datetime) -> list[BehaviorEvent]:
        result = await self._session.execute(
            select(AiBehaviorEventModel)
            .where(
                AiBehaviorEventModel.user_id == user_id,
                AiBehaviorEventModel.created_at >= since,
            )
            .order_by(AiBehaviorEventModel.created_at, AiBehaviorEventModel.id)
        )
        return [
            BehaviorEvent(
                type=m.type,  # type: ignore[arg-type]
                created_at=m.created_at,
                todo_id=m.todo_id,
                data=dict(m.data or {}),
            )
            for m in result.scalars()
        ]

    async def find_model(self, user_id: str) -> tuple[BehaviorModel, datetime, bool] | None:
        m = await self._session.get(AiUserModelModel, user_id, populate_existing=True)
        if m is None:
            return None
        return BehaviorModel.from_json(dict(m.model)), m.computed_at, m.stale

    async def save_model(self, user_id: str, model: BehaviorModel, computed_at: datetime) -> None:
        stmt = insert(AiUserModelModel).values(
            user_id=user_id, model=model.to_json(), computed_at=computed_at, stale=False
        )
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[AiUserModelModel.user_id],
                set_={"model": stmt.excluded.model, "computed_at": computed_at, "stale": False},
            )
        )

    async def reset(self, user_id: str) -> None:
        await self._session.execute(
            delete(AiBehaviorEventModel).where(AiBehaviorEventModel.user_id == user_id)
        )
        await self._session.execute(
            delete(AiUserModelModel).where(AiUserModelModel.user_id == user_id)
        )

    async def purge_before(self, before: datetime) -> int:
        result = await self._session.execute(
            delete(AiBehaviorEventModel).where(AiBehaviorEventModel.created_at < before)
        )
        deleted = int(result.rowcount or 0)  # type: ignore[attr-defined]
        if deleted:
            # 통계는 다음 추천 때 다시 계산되도록(지운 기록이 남아 있지 않게).
            await self._session.execute(update(AiUserModelModel).values(stale=True))
        return deleted
