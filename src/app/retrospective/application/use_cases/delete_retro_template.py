from datetime import datetime, timezone

from app.retrospective.application.dtos.retro_template_commands import DeleteRetroTemplateCommand
from app.retrospective.domain.exceptions.exceptions import (
    RetroTemplateDefaultNotDeletableException,
    RetroTemplateNotFoundException,
)
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository
from app.settings.domain.repositories.repository import IUserSettingsRepository


class DeleteRetroTemplateUseCase:
    def __init__(
        self,
        template_repo: IRetroTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._template_repo = template_repo
        self._settings_repo = settings_repo

    async def execute(self, cmd: DeleteRetroTemplateCommand) -> None:
        template = await self._template_repo.find_by_id(cmd.template_id, cmd.user_id)
        if template is None:
            raise RetroTemplateNotFoundException()

        if template.is_default:
            raise RetroTemplateDefaultNotDeletableException()

        # 활성 템플릿이면 기본 템플릿으로 자동 폴백
        settings = await self._settings_repo.find_by_user_id(cmd.user_id)
        if settings is not None:
            active_id = settings.active_retro_template_id_for(template.retro_type.value)
            if active_id == template.id:
                default = await self._template_repo.find_default_for_type(
                    cmd.user_id, template.retro_type
                )
                fallback_id = default.id if default else None
                settings.active_retro_template_ids[template.retro_type.value] = fallback_id
                settings.updated_at = datetime.now(timezone.utc)
                await self._settings_repo.save(settings)

        await self._template_repo.delete(cmd.template_id, cmd.user_id)
