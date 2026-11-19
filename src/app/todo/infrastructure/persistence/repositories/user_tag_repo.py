from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.todo.domain.models.user_tag import UserTag
from app.todo.domain.repositories.repository import IUserTagRepository
from app.todo.infrastructure.persistence.models.user_tag_model import UserTagModel


class UserTagRepository(IUserTagRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: str) -> list[UserTag]:
        result = await self._session.execute(
            select(UserTagModel).where(UserTagModel.user_id == user_id)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_name(self, user_id: str, name: str) -> UserTag | None:
        result = await self._session.execute(
            select(UserTagModel).where(UserTagModel.user_id == user_id, UserTagModel.name == name)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def save(self, tag: UserTag) -> UserTag:
        merged = await self._session.merge(
            UserTagModel(
                id=tag.id,
                user_id=tag.user_id,
                name=tag.name,
                color=tag.color,
                sort_order=tag.sort_order,
                created_at=tag.created_at,
            )
        )
        await self._session.flush()
        return self._to_entity(merged)

    async def delete_by_name(self, user_id: str, name: str) -> None:
        await self._session.execute(
            delete(UserTagModel).where(UserTagModel.user_id == user_id, UserTagModel.name == name)
        )

    @staticmethod
    def _to_entity(m: UserTagModel) -> UserTag:
        return UserTag(
            id=m.id,
            user_id=m.user_id,
            name=m.name,
            color=m.color,
            sort_order=m.sort_order,
            created_at=m.created_at,
        )
