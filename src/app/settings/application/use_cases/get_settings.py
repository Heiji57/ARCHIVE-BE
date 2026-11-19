from dataclasses import replace

from app.retrospective.domain.repositories.repository import IFolderRepository
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository

_DEFAULT_RETRO_FOLDER_KEY = "defaultRetroFolderId"


class GetSettingsUseCase:
    def __init__(self, repo: IUserSettingsRepository, folder_repo: IFolderRepository) -> None:
        self._repo = repo
        self._folder_repo = folder_repo

    async def execute(self, user_id: str) -> UserSettings:
        settings = await self._repo.find_by_user_id(user_id)
        if settings is None:
            return UserSettings.default(user_id)
        return await self._without_dangling_folder(settings)

    async def _without_dangling_folder(self, settings: UserSettings) -> UserSettings:
        """새 회고 기본 폴더가 지워진 폴더를 가리키면 응답에서만 null 로 내린다(저장값은 그대로)."""
        folder_id = settings.ui_preferences.get(_DEFAULT_RETRO_FOLDER_KEY)
        if not isinstance(folder_id, str):
            return settings
        if await self._folder_repo.find_by_id(folder_id, settings.user_id) is not None:
            return settings
        return replace(
            settings,
            ui_preferences={**settings.ui_preferences, _DEFAULT_RETRO_FOLDER_KEY: None},
        )
