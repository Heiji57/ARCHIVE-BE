from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.exceptions.exceptions import JournalEntryAlreadyExistsException
from app.retrospective.domain.models.journal_entry import JournalEntry, JournalEntryMeta
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.retrospective.infrastructure.persistence.models.folder_model import (
    FolderModel,  # noqa: F401
)
from app.retrospective.infrastructure.persistence.models.journal_entry_model import (
    JournalEntryModel,
)
from app.shared.infrastructure.database.errors import translate_unique_violations
from app.shared.infrastructure.database.soft_delete import INCLUDE_DELETED

# 사전 중복 체크를 동시 요청이 함께 통과했을 때 — 늦은 쪽도 같은 409 를 받게 한다.
_UNIQUE_VIOLATIONS = {
    "uq_journal_entries_user_date_retro_type": JournalEntryAlreadyExistsException,
}


class JournalEntryRepository(IJournalEntryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: JournalEntry) -> JournalEntry:
        model = self._to_model(entry)
        async with translate_unique_violations(_UNIQUE_VIOLATIONS):
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

    async def find_meta_by_ids(self, user_id: str, ids: list[str]) -> list[JournalEntryMeta]:
        if not ids:
            return []
        # content / content_tsv 를 제외한 컬럼만 SELECT — 주제 매칭은 본문을 읽지 않는다.
        result = await self._session.execute(
            select(
                JournalEntryModel.id,
                JournalEntryModel.date_key,
                JournalEntryModel.title,
                JournalEntryModel.retro_type,
            ).where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.id.in_(ids),
            )
        )
        return [
            JournalEntryMeta(
                id=row.id,
                date_key=row.date_key,
                title=row.title,
                retro_type=RetroType(row.retro_type),
            )
            for row in result.all()
        ]

    async def id_exists(self, id: str) -> bool:
        # 휴지통의 회고도 센다 — 다른 사용자가 같은 id 로 PUT 해 덮지 못하게(IDOR 가드).
        result = await self._session.execute(
            select(JournalEntryModel.id)
            .where(JournalEntryModel.id == id)
            .limit(1)
            .execution_options(**INCLUDE_DELETED)
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
            # select_from 이 있어야 휴지통 조건(with_loader_criteria)이 붙는다 — 엔티티가 FROM 에
            # 명시되지 않은 count 는 ORM 엔티티 문장으로 취급되지 않는다.
            select(func.count())
            .select_from(JournalEntryModel)
            .where(JournalEntryModel.user_id == user_id)
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

    # ── 휴지통 ────────────────────────────────────────────────────────────────

    async def soft_delete(self, id: str, user_id: str) -> None:
        await self._session.execute(
            update(JournalEntryModel)
            .where(JournalEntryModel.id == id, JournalEntryModel.user_id == user_id)
            .values(deleted_at=func.now())
        )

    async def soft_delete_in_folders(self, user_id: str, folder_ids: list[str]) -> list[str]:
        if not folder_ids:
            return []
        result = await self._session.execute(
            update(JournalEntryModel)
            .where(
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.folder_id.in_(folder_ids),
            )
            .values(deleted_at=func.now())
            .returning(JournalEntryModel.id)
        )
        return list(result.scalars())

    async def list_trashed(self, user_id: str) -> list[JournalEntry]:
        result = await self._session.execute(
            select(JournalEntryModel)
            .where(JournalEntryModel.user_id == user_id, JournalEntryModel.deleted_at.is_not(None))
            .order_by(JournalEntryModel.deleted_at.desc())
            .execution_options(**INCLUDE_DELETED)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_trashed(self, id: str, user_id: str) -> JournalEntry | None:
        result = await self._session.execute(
            select(JournalEntryModel)
            .where(
                JournalEntryModel.id == id,
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.deleted_at.is_not(None),
            )
            .execution_options(**INCLUDE_DELETED)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def restore(self, id: str, user_id: str) -> None:
        # 폴더가 지워졌으면 folder_id 는 FK(SET NULL)로 이미 비어 "미분류"로 돌아온다.
        # 같은 날 같은 종류의 새 회고가 이미 있으면 부분 유니크 인덱스가 막는다 → 409.
        async with translate_unique_violations(_UNIQUE_VIOLATIONS):
            await self._session.execute(
                update(JournalEntryModel)
                .where(
                    JournalEntryModel.id == id,
                    JournalEntryModel.user_id == user_id,
                    JournalEntryModel.deleted_at.is_not(None),
                )
                .values(deleted_at=None)
                .execution_options(**INCLUDE_DELETED)
            )
            await self._session.flush()

    async def purge(self, id: str, user_id: str) -> list[str]:
        result = await self._session.execute(
            delete(JournalEntryModel)
            .where(
                JournalEntryModel.id == id,
                JournalEntryModel.user_id == user_id,
                JournalEntryModel.deleted_at.is_not(None),
            )
            .returning(JournalEntryModel.id)
            .execution_options(**INCLUDE_DELETED)
        )
        return list(result.scalars())

    async def purge_trashed(self, user_id: str | None, before: datetime | None) -> list[str]:
        conditions: list[Any] = [JournalEntryModel.deleted_at.is_not(None)]
        if user_id is not None:
            conditions.append(JournalEntryModel.user_id == user_id)
        if before is not None:
            conditions.append(JournalEntryModel.deleted_at < before)
        result = await self._session.execute(
            delete(JournalEntryModel)
            .where(*conditions)
            .returning(JournalEntryModel.id)
            .execution_options(**INCLUDE_DELETED)
        )
        return list(result.scalars())

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
            deleted_at=model.deleted_at,
        )
