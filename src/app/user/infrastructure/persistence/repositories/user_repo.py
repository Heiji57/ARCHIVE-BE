from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.database.errors import translate_unique_violations
from app.user.domain.exceptions.exceptions import UserEmailDuplicatedException
from app.user.domain.models.user import User
from app.user.domain.models.value_objects import Email
from app.user.domain.repositories.repository import IUserRepository
from app.user.infrastructure.persistence.models.user_model import UserModel

# 사전 중복 체크를 동시 요청이 함께 통과했을 때 — 늦은 쪽도 같은 409 를 받게 한다.
_UNIQUE_VIOLATIONS = {
    "users_email_key": UserEmailDuplicatedException,
}


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user: User) -> User:
        model = self._to_model(user)
        async with translate_unique_violations(_UNIQUE_VIOLATIONS):
            merged = await self._session.merge(model)
            await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str) -> User | None:
        result = await self._session.get(UserModel, id)
        return self._to_entity(result) if result else None

    async def find_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def delete(self, id: str) -> None:
        model = await self._session.get(UserModel, id)
        if model:
            await self._session.delete(model)

    def _to_model(self, entity: User) -> UserModel:
        return UserModel(
            id=entity.id,
            email=str(entity.email),
            password_hash=entity.password_hash,
            country=entity.country,
            region=entity.region,
            timezone=entity.timezone,
            account_type=entity.account_type,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: UserModel) -> User:
        return User(
            id=model.id,
            email=Email(model.email),
            password_hash=model.password_hash,
            country=model.country,
            region=model.region,
            timezone=model.timezone,
            account_type=model.account_type,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
