from datetime import datetime, timezone

from app.retrospective.application.dtos.retro_template_commands import SetActiveRetroTemplateCommand
from app.retrospective.domain.exceptions.exceptions import (
    RetroTemplateNotFoundException,
    RetroTemplateTypeMismatchException,
)
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository


class SetActiveRetroTemplateUseCase:
    def __init__(
        self,
        template_repo: IRetroTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._template_repo = template_repo
        self._settings_repo = settings_repo

    async def execute(self, cmd: SetActiveRetroTemplateCommand) -> UserSettings:
        template = await self._template_repo.find_by_id(cmd.template_id, cmd.user_id)
        if template is None:
            raise RetroTemplateNotFoundException()

        if template.retro_type != cmd.retro_type:
            raise RetroTemplateTypeMismatchException()

        settings = await self._settings_repo.find_by_user_id(cmd.user_id)
        if settings is None:
            settings = UserSettings.default(cmd.user_id)

        settings.active_retro_template_ids[cmd.retro_type.value] = cmd.template_id
        settings.updated_at = datetime.now(timezone.utc)
        return await self._settings_repo.save(settings)
