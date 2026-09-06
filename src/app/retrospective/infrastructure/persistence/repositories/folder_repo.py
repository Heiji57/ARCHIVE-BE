from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.folder import Folder
from app.retrospective.domain.repositories.repository import IFolderRepository
from app.retrospective.infrastructure.persistence.models.folder_model import FolderModel


class FolderRepository(IFolderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, folder: Folder) -> Folder:
        model = self._to_model(folder)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str, user_id: str) -> Folder | None:
        result = await self._session.execute(
            select(FolderModel).where(FolderModel.id == id, FolderModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_name(
        self, user_id: str, parent_folder_id: str | None, name: str
    ) -> Folder | None:
        stmt = select(FolderModel).where(
            FolderModel.user_id == user_id, FolderModel.name == name
        )
        if parent_folder_id is None:
            stmt = stmt.where(FolderModel.parent_folder_id.is_(None))
        else:
            stmt = stmt.where(FolderModel.parent_folder_id == parent_folder_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_children(
        self, user_id: str, parent_folder_id: str | None
    ) -> list[Folder]:
        stmt = self._children_scope(user_id, parent_folder_id)
        result = await self._session.execute(stmt.order_by(FolderModel.name))
        return [self._to_entity(m) for m in result.scalars()]

    async def find_all(self, user_id: str, limit: int) -> list[Folder]:
        if limit <= 0:
            return []
        result = await self._session.execute(
            select(FolderModel)
            .where(FolderModel.user_id == user_id)
            .order_by(FolderModel.name.asc(), FolderModel.id.asc())
            .limit(limit)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_children_page(
        self, user_id: str, parent_folder_id: str | None, offset: int, limit: int
    ) -> list[Folder]:
        if limit <= 0:
            return []
        stmt = self._children_scope(user_id, parent_folder_id)
        result = await self._session.execute(
            stmt.order_by(FolderModel.name.asc(), FolderModel.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def count_children(self, user_id: str, parent_folder_id: str | None) -> int:
        stmt = self._children_scope(user_id, parent_folder_id)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return total or 0

    def _children_scope(
        self, user_id: str, parent_folder_id: str | None
    ) -> Select[tuple[FolderModel]]:
        stmt = select(FolderModel).where(FolderModel.user_id == user_id)
        if parent_folder_id is None:
            stmt = stmt.where(FolderModel.parent_folder_id.is_(None))
        else:
            stmt = stmt.where(FolderModel.parent_folder_id == parent_folder_id)
        return stmt

    async def count_children_by_parent_ids(
        self, user_id: str, parent_ids: list[str]
    ) -> dict[str, int]:
        if not parent_ids:
            return {}
        result = await self._session.execute(
            select(FolderModel.parent_folder_id, func.count())
            .where(
                FolderModel.user_id == user_id,
                FolderModel.parent_folder_id.in_(parent_ids),
            )
            .group_by(FolderModel.parent_folder_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def find_ancestors(self, folder_id: str, user_id: str) -> list[Folder]:
        ancestors: list[Folder] = []
        current_id: str | None = folder_id
        seen: set[str] = {folder_id}
        while current_id is not None:
            folder = await self.find_by_id(current_id, user_id)
            if folder is None or folder.parent_folder_id is None:
                break
            if folder.parent_folder_id in seen:
                break
            parent = await self.find_by_id(folder.parent_folder_id, user_id)
            if parent is None:
                break
            ancestors.append(parent)
            seen.add(parent.id)
            current_id = parent.id
        return ancestors

    async def delete(self, id: str, user_id: str) -> None:
        result = await self._session.execute(
            select(FolderModel).where(FolderModel.id == id, FolderModel.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row:
            await self._session.delete(row)

    def _to_model(self, entity: Folder) -> FolderModel:
        return FolderModel(
            id=entity.id,
            user_id=entity.user_id,
            parent_folder_id=entity.parent_folder_id,
            name=entity.name,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: FolderModel) -> Folder:
        return Folder(
            id=model.id,
            user_id=model.user_id,
            parent_folder_id=model.parent_folder_id,
            name=model.name,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
