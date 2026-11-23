from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.domain.models.learning import VISIBILITY_EVENTS, BehaviorEvent, BehaviorModel
from app.ai.domain.repositories.repository import IBehaviorRepository
from app.ai.infrastructure.persistence.models.learning_model import (
    AiBehaviorEventModel,
    AiUserModelModel,
)
from app.shared.domain.utils.id import generate_id


class BehaviorRepository(IBehaviorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_event(self, user_id: str, event: BehaviorEvent) -> None:
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

    async def event_signature(self, user_id: str) -> str:
        await self._session.flush()
        count, last = (
            await self._session.execute(
                select(func.count(), func.max(AiBehaviorEventModel.id)).where(
                    AiBehaviorEventModel.user_id == user_id,
                    AiBehaviorEventModel.type.not_in(VISIBILITY_EVENTS),
                )
            )
        ).one()
        return f"{count}:{last or ''}"

    async def delete_by_source(
        self, user_id: str, source: str, todo_ids: list[str] | None = None
    ) -> None:
        stmt = delete(AiBehaviorEventModel).where(
            AiBehaviorEventModel.user_id == user_id,
            AiBehaviorEventModel.data["source"].astext == source,
        )
        if todo_ids is not None:
            stmt = stmt.where(AiBehaviorEventModel.todo_id.in_(todo_ids))
        await self._session.execute(stmt)

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

    async def find_model(self, user_id: str) -> tuple[BehaviorModel, datetime, str] | None:
        m = await self._session.get(AiUserModelModel, user_id, populate_existing=True)
        if m is None:
            return None
        return BehaviorModel.from_json(dict(m.model)), m.computed_at, m.signature

    async def save_model(
        self, user_id: str, model: BehaviorModel, computed_at: datetime, signature: str
    ) -> None:
        stmt = insert(AiUserModelModel).values(
            user_id=user_id, model=model.to_json(), computed_at=computed_at, signature=signature
        )
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[AiUserModelModel.user_id],
                set_={
                    "model": stmt.excluded.model,
                    "computed_at": computed_at,
                    "signature": signature,
                },
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
        # 지우면 기록 서명이 바뀌어 다음 추천 때 다시 계산된다.
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
