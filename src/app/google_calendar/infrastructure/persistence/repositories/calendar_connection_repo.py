from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.google_calendar.domain.models.calendar_connection import GoogleCalendarConnection
from app.google_calendar.domain.repositories.repository import (
    IGoogleCalendarConnectionRepository,
)
from app.google_calendar.infrastructure.persistence.models.calendar_connection_model import (
    GoogleCalendarConnectionModel,
)


class GoogleCalendarConnectionRepository(IGoogleCalendarConnectionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_user_id(self, user_id: str) -> GoogleCalendarConnection | None:
        result = await self._session.execute(
            select(GoogleCalendarConnectionModel).where(
                GoogleCalendarConnectionModel.user_id == user_id
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def save(self, connection: GoogleCalendarConnection) -> GoogleCalendarConnection:
        merged = await self._session.merge(self._to_model(connection))
        await self._session.flush()
        return self._to_entity(merged)

    async def delete_by_user_id(self, user_id: str) -> None:
        await self._session.execute(
            delete(GoogleCalendarConnectionModel).where(
                GoogleCalendarConnectionModel.user_id == user_id
            )
        )

    async def find_active_user_ids(self, active_since: datetime) -> list[str]:
        result = await self._session.execute(
            select(GoogleCalendarConnectionModel.user_id).where(
                GoogleCalendarConnectionModel.needs_reauth.is_(False),
                GoogleCalendarConnectionModel.last_active_at.is_not(None),
                GoogleCalendarConnectionModel.last_active_at >= active_since,
            )
        )
        return list(result.scalars())

    async def touch_last_active(self, user_id: str, now: datetime) -> None:
        await self._session.execute(
            update(GoogleCalendarConnectionModel)
            .where(GoogleCalendarConnectionModel.user_id == user_id)
            .values(last_active_at=now)
        )

    def _to_model(
        self, entity: GoogleCalendarConnection
    ) -> GoogleCalendarConnectionModel:
        return GoogleCalendarConnectionModel(
            id=entity.id,
            user_id=entity.user_id,
            google_user_id=entity.google_user_id,
            access_token=entity.access_token,
            refresh_token=entity.refresh_token,
            token_expires_at=entity.token_expires_at,
            scope=entity.scope,
            sync_token=entity.sync_token,
            last_synced_at=entity.last_synced_at,
            last_active_at=entity.last_active_at,
            needs_reauth=entity.needs_reauth,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(
        self, model: GoogleCalendarConnectionModel
    ) -> GoogleCalendarConnection:
        return GoogleCalendarConnection(
            id=model.id,
            user_id=model.user_id,
            google_user_id=model.google_user_id,
            access_token=model.access_token,
            refresh_token=model.refresh_token,
            token_expires_at=model.token_expires_at,
            scope=model.scope,
            sync_token=model.sync_token,
            last_synced_at=model.last_synced_at,
            last_active_at=model.last_active_at,
            needs_reauth=model.needs_reauth,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
