from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.retrospective.infrastructure.persistence.models.journal_entry_model import JournalEntryModel


class JournalEntryRepository(IJournalEntryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: JournalEntry) -> JournalEntry:
        model = self._to_model(entry)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str, user_id: str) -> JournalEntry | None:
        result = await self._session.execute(
            select(JournalEntryModel).where(
                JournalEntryModel.id == id, JournalEntryModel.user_id == user_id
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_date_key(self, user_id: str, date_key: str) -> JournalEntry | None:
        result = await self._session.execute(
            select(JournalEntryModel).where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.date_key == date_key,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_period(self, user_id: str, start: date, end: date) -> list[JournalEntry]:
        result = await self._session.execute(
            select(JournalEntryModel)
            .where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.date_key >= start.isoformat(),
                JournalEntryModel.date_key <= end.isoformat(),
            )
            .order_by(JournalEntryModel.date_key)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_retro_type(self, user_id: str, retro_type: str) -> list[JournalEntry]:
        result = await self._session.execute(
            select(JournalEntryModel)
            .where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.retro_type == retro_type,
            )
            .order_by(JournalEntryModel.date_key.desc())
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[JournalEntry], int]:
        stmt = (
            select(JournalEntryModel)
            .where(JournalEntryModel.user_id == user_id)
            .where(JournalEntryModel.content_tsv.match(query))  # type: ignore[union-attr]
        )
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        result = await self._session.execute(
            stmt.order_by(JournalEntryModel.updated_at.desc()).offset((page - 1) * size).limit(size)
        )
        return [self._to_entity(m) for m in result.scalars()], total or 0

    async def delete(self, id: str, user_id: str) -> None:
        result = await self._session.execute(
            select(JournalEntryModel).where(
                JournalEntryModel.id == id, JournalEntryModel.user_id == user_id
            )
        )
        row = result.scalar_one_or_none()
        if row:
            await self._session.delete(row)

    def _to_model(self, entity: JournalEntry) -> JournalEntryModel:
        return JournalEntryModel(
            id=entity.id,
            user_id=entity.user_id,
            date_key=entity.date_key,
            title=entity.title,
            content=entity.content,
            retro_type=entity.retro_type.value,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: JournalEntryModel) -> JournalEntry:
        return JournalEntry(
            id=model.id,
            user_id=model.user_id,
            date_key=model.date_key,
            title=model.title,
            content=model.content,
            retro_type=RetroType(model.retro_type),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
