from datetime import date, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.domain.models.ai_settings import SOURCES, AiMemory, AiSchedule, AiSettings
from app.ai.domain.repositories.repository import IAiRetentionRepository, IAiSettingsRepository
from app.ai.infrastructure.persistence.models.ai_settings_model import (
    AiMemoryModel,
    AiScheduleModel,
    AiSettingsModel,
)
from app.ai.infrastructure.persistence.models.conversation_model import (
    AiConversationModel,
    AiProposalModel,
)


class AiSettingsRepository(IAiSettingsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, user_id: str) -> AiSettings | None:
        m = await self._session.get(AiSettingsModel, user_id)
        if m is None:
            return None
        return AiSettings(
            user_id=m.user_id,
            pet_enabled=m.pet_enabled,
            tools={s: bool((m.tools or {}).get(s, True)) for s in SOURCES},
            confirm_mode="always",
            answer_length=m.answer_length,  # type: ignore[arg-type]
            deep_search=m.deep_search,
            memory_enabled=m.memory_enabled,
            retention_days=m.retention_days,
        )

    async def save(self, s: AiSettings) -> AiSettings:
        await self._session.merge(
            AiSettingsModel(
                user_id=s.user_id,
                pet_enabled=s.pet_enabled,
                tools=dict(s.tools),
                confirm_mode=s.confirm_mode,
                answer_length=s.answer_length,
                deep_search=s.deep_search,
                memory_enabled=s.memory_enabled,
                retention_days=s.retention_days,
                updated_at=datetime.now().astimezone(),
            )
        )
        await self._session.flush()
        return s

    async def list_memories(self, user_id: str) -> list[AiMemory]:
        result = await self._session.execute(
            select(AiMemoryModel)
            .where(AiMemoryModel.user_id == user_id)
            .order_by(AiMemoryModel.created_at)
        )
        return [
            AiMemory(id=m.id, user_id=m.user_id, text=m.text, created_at=m.created_at)
            for m in result.scalars()
        ]

    async def add_memory(self, memory: AiMemory) -> AiMemory:
        self._session.add(
            AiMemoryModel(
                id=memory.id, user_id=memory.user_id, text=memory.text, created_at=memory.created_at
            )
        )
        await self._session.flush()
        return memory

    async def delete_memory(self, memory_id: str, user_id: str) -> bool:
        result = await self._session.execute(
            delete(AiMemoryModel).where(
                AiMemoryModel.id == memory_id, AiMemoryModel.user_id == user_id
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def list_schedules(self, user_id: str) -> list[AiSchedule]:
        result = await self._session.execute(
            select(AiScheduleModel)
            .where(AiScheduleModel.user_id == user_id)
            .order_by(AiScheduleModel.created_at)
        )
        return [self._schedule(m) for m in result.scalars()]

    async def find_schedule(self, schedule_id: str, user_id: str) -> AiSchedule | None:
        result = await self._session.execute(
            select(AiScheduleModel).where(
                AiScheduleModel.id == schedule_id, AiScheduleModel.user_id == user_id
            )
        )
        m = result.scalar_one_or_none()
        return self._schedule(m) if m else None

    async def save_schedule(self, s: AiSchedule) -> AiSchedule:
        merged = await self._session.merge(
            AiScheduleModel(
                id=s.id,
                user_id=s.user_id,
                prompt=s.prompt,
                repeat=dict(s.repeat),
                enabled=s.enabled,
                last_run_date=s.last_run_date,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
        )
        await self._session.flush()
        return self._schedule(merged)

    async def delete_schedule(self, schedule_id: str, user_id: str) -> bool:
        result = await self._session.execute(
            delete(AiScheduleModel).where(
                AiScheduleModel.id == schedule_id, AiScheduleModel.user_id == user_id
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def claim_run(self, schedule_id: str, run_date: date) -> bool:
        result = await self._session.execute(
            update(AiScheduleModel)
            .where(
                AiScheduleModel.id == schedule_id,
                AiScheduleModel.enabled.is_(True),
                or_(
                    AiScheduleModel.last_run_date.is_(None),
                    AiScheduleModel.last_run_date != run_date,
                ),
            )
            .values(last_run_date=run_date)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def list_enabled_schedules(self) -> list[AiSchedule]:
        result = await self._session.execute(
            select(AiScheduleModel).where(AiScheduleModel.enabled.is_(True))
        )
        return [self._schedule(m) for m in result.scalars()]

    @staticmethod
    def _schedule(m: AiScheduleModel) -> AiSchedule:
        return AiSchedule(
            id=m.id,
            user_id=m.user_id,
            prompt=m.prompt,
            repeat=dict(m.repeat),
            enabled=m.enabled,
            last_run_date=m.last_run_date,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class AiRetentionRepository(IAiRetentionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge_older_than(self, user_id: str, before: datetime) -> int:
        last = func.coalesce(AiConversationModel.updated_at, AiConversationModel.created_at)
        result = await self._session.execute(
            delete(AiConversationModel).where(AiConversationModel.user_id == user_id, last < before)
        )
        await self._session.execute(
            delete(AiProposalModel).where(
                AiProposalModel.user_id == user_id,
                AiProposalModel.status.in_(["pending", "dismissed"]),
                AiProposalModel.created_at < before,
            )
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
