from abc import ABC, abstractmethod

from app.settings.domain.models.user_settings import UserSettings


class IUserSettingsRepository(ABC):
    @abstractmethod
    async def find_by_user_id(self, user_id: str) -> UserSettings | None: ...

    @abstractmethod
    async def save(self, settings: UserSettings) -> UserSettings: ...
