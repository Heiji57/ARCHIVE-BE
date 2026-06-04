from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.utils.id import generate_id
from app.user.domain.models.country_history import (
    CountryChangeRecord,
    CountryChangeSource,
)
from app.user.domain.repositories.country_history_repository import (
    ICountryHistoryRepository,
)
from app.user.infrastructure.persistence.models.country_history_model import (
    UserCountryHistoryModel,
)


class CountryHistoryRepository(ICountryHistoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        user_id: str,
        country: str,
        region: str | None,
        timezone: str,
        source: CountryChangeSource,
        at: datetime,
    ) -> CountryChangeRecord:
        model = UserCountryHistoryModel(
            id=generate_id("uch"),
            user_id=user_id,
            country=country,
            region=region,
            timezone=timezone,
            source=source.value,
            created_at=at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def list_by_user(self, user_id: str) -> list[CountryChangeRecord]:
        result = await self._session.execute(
            select(UserCountryHistoryModel)
            .where(UserCountryHistoryModel.user_id == user_id)
            .order_by(UserCountryHistoryModel.created_at.desc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    @staticmethod
    def _to_entity(model: UserCountryHistoryModel) -> CountryChangeRecord:
        return CountryChangeRecord(
            id=model.id,
            user_id=model.user_id,
            country=model.country,
            region=model.region,
            timezone=model.timezone,
            source=CountryChangeSource(model.source),
            created_at=model.created_at,
        )
