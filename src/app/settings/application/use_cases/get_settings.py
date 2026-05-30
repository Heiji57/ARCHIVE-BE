from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository


class GetSettingsUseCase:
    def __init__(self, repo: IUserSettingsRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> UserSettings:
        settings = await self._repo.find_by_user_id(user_id)
        return settings if settings is not None else UserSettings.default(user_id)
