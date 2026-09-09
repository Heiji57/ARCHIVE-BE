from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.retrospective.infrastructure.persistence.models.folder_model import FolderModel  # noqa: F401
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

    async def find_by_ids(self, user_id: str, ids: list[str]) -> list[JournalEntry]:
        if not ids:
            return []
        result = await self._session.execute(
            select(JournalEntryModel).where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.id.in_(ids),
            )
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def id_exists(self, id: str) -> bool:
        result = await self._session.execute(
            select(JournalEntryModel.id).where(JournalEntryModel.id == id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def find_by_date_key(self, user_id: str, date_key: str, retro_type: str) -> JournalEntry | None:
        result = await self._session.execute(
            select(JournalEntryModel).where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.date_key == date_key,
                JournalEntryModel.retro_type == retro_type,
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

    async def find_by_retro_type(
        self, user_id: str, retro_type: str, since: date
    ) -> list[JournalEntry]:
        result = await self._session.execute(
            select(JournalEntryModel)
            .where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.retro_type == retro_type,
                JournalEntryModel.date_key >= since.isoformat(),
            )
            .order_by(JournalEntryModel.date_key.desc())
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_page(
        self,
        user_id: str,
        retro_type: str | None,
        page: int,
        size: int,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[JournalEntry], int]:
        stmt = select(JournalEntryModel).where(JournalEntryModel.user_id == user_id)
        if retro_type:
            stmt = stmt.where(JournalEntryModel.retro_type == retro_type)
        if q:
            stmt = stmt.where(JournalEntryModel.content_tsv.match(q))  # type: ignore[union-attr]
        if from_date:
            stmt = stmt.where(JournalEntryModel.date_key >= from_date.isoformat())
        if to_date:
            stmt = stmt.where(JournalEntryModel.date_key <= to_date.isoformat())
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        result = await self._session.execute(
            stmt.order_by(JournalEntryModel.date_key.desc(), JournalEntryModel.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return [self._to_entity(m) for m in result.scalars()], total or 0

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

    async def find_by_folder_page(
        self,
        user_id: str,
        folder_id: str | None,
        retro_type: str | None,
        offset: int,
        limit: int,
    ) -> list[JournalEntry]:
        if limit <= 0:
            return []
        stmt = self._folder_scope(user_id, folder_id, retro_type)
        result = await self._session.execute(
            stmt.order_by(JournalEntryModel.date_key.desc(), JournalEntryModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def count_by_folder(
        self, user_id: str, folder_id: str | None, retro_type: str | None = None
    ) -> int:
        stmt = self._folder_scope(user_id, folder_id, retro_type)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return total or 0

    def _folder_scope(
        self, user_id: str, folder_id: str | None, retro_type: str | None
    ) -> Select[tuple[JournalEntryModel]]:
        stmt = select(JournalEntryModel).where(JournalEntryModel.user_id == user_id)
        stmt = stmt.where(
            JournalEntryModel.folder_id.is_(None)
            if folder_id is None
            else JournalEntryModel.folder_id == folder_id
        )
        if retro_type:
            stmt = stmt.where(JournalEntryModel.retro_type == retro_type)
        return stmt

    async def count_by_folder_ids(
        self, user_id: str, folder_ids: list[str]
    ) -> dict[str, int]:
        if not folder_ids:
            return {}
        result = await self._session.execute(
            select(JournalEntryModel.folder_id, func.count())
            .where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.folder_id.in_(folder_ids),
            )
            .group_by(JournalEntryModel.folder_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_all_by_user_id(self, user_id: str) -> int:
        result = await self._session.scalar(
            select(func.count()).where(JournalEntryModel.user_id == user_id)
        )
        return result or 0

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
            folder_id=entity.folder_id,
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
            folder_id=model.folder_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
