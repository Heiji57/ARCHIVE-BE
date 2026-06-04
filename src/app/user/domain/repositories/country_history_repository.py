"""국가 변경 이력 repository ABC."""
from abc import ABC, abstractmethod
from datetime import datetime

from app.user.domain.models.country_history import (
    CountryChangeRecord,
    CountryChangeSource,
)

__all__ = [
    "ICountryHistoryRepository",
    "CountryChangeSource",
    "CountryChangeRecord",
]


class ICountryHistoryRepository(ABC):
    @abstractmethod
    async def record(
        self,
        user_id: str,
        country: str,
        region: str | None,
        timezone: str,
        source: CountryChangeSource,
        at: datetime,
    ) -> CountryChangeRecord: ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[CountryChangeRecord]: ...
