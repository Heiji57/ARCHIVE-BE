from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.domain.models.oauth_connection import OAuthConnection
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.auth.infrastructure.persistence.models.oauth_connection_model import OAuthConnectionModel


class OAuthConnectionRepository(IOAuthConnectionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, connection: OAuthConnection) -> OAuthConnection:
        model = self._to_model(connection)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_provider(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> OAuthConnection | None:
        result = await self._session.execute(
            select(OAuthConnectionModel).where(
                OAuthConnectionModel.provider == provider,
                OAuthConnectionModel.provider_user_id == provider_user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_user_id(self, user_id: str) -> list[OAuthConnection]:
        result = await self._session.execute(
            select(OAuthConnectionModel).where(OAuthConnectionModel.user_id == user_id)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, id: str) -> None:
        model = await self._session.get(OAuthConnectionModel, id)
        if model:
            await self._session.delete(model)

    def _to_model(self, entity: OAuthConnection) -> OAuthConnectionModel:
        return OAuthConnectionModel(
            id=entity.id,
            user_id=entity.user_id,
            provider=entity.provider,
            provider_user_id=entity.provider_user_id,
            access_token=entity.access_token,
            provider_login=entity.provider_login,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: OAuthConnectionModel) -> OAuthConnection:
        return OAuthConnection(
            id=model.id,
            user_id=model.user_id,
            provider=OAuthProvider(model.provider),
            provider_user_id=model.provider_user_id,
            access_token=model.access_token,
            provider_login=model.provider_login,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
