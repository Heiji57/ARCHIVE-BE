from app.retrospective.application.dtos.template_commands import (
    DeleteSummaryTemplateCommand,
)
from app.retrospective.domain.exceptions.exceptions import (
    SummaryTemplateInUseException,
    SummaryTemplateNotFoundException,
)
from app.retrospective.domain.repositories.repository import (
    IUserSummaryTemplateRepository,
)
from app.settings.domain.repositories.repository import IUserSettingsRepository


class DeleteSummaryTemplateUseCase:
    def __init__(
        self,
        template_repo: IUserSummaryTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._template_repo = template_repo
        self._settings_repo = settings_repo

    async def execute(self, cmd: DeleteSummaryTemplateCommand) -> None:
        existing = await self._template_repo.find_by_id(cmd.template_id, cmd.user_id)
        if existing is None:
            raise SummaryTemplateNotFoundException()

        # 활성 보호 — user_settings.active_summary_template_ids 의 값과 매칭되면 차단
        settings = await self._settings_repo.find_by_user_id(cmd.user_id)
        if settings is not None:
            active_id = settings.active_template_id_for(existing.summary_type.value)
            if active_id == existing.id:
                raise SummaryTemplateInUseException(
                    f"Template is currently active for {existing.summary_type.value}; "
                    f"deactivate it first."
                )

        await self._template_repo.delete(cmd.template_id, cmd.user_id)
