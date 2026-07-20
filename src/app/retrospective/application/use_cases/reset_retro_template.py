from datetime import datetime, timezone

from app.retrospective.application.dtos.retro_template_commands import ResetRetroTemplateCommand
from app.retrospective.domain.constants.retro_template_defaults import DEFAULT_CONTENT
from app.retrospective.domain.exceptions.exceptions import (
    RetroTemplateDefaultNotDeletableException,
    RetroTemplateNotFoundException,
)
from app.retrospective.domain.models.retro_template import RetroTemplate
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository


class ResetRetroTemplateUseCase:
    def __init__(self, repo: IRetroTemplateRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: ResetRetroTemplateCommand) -> RetroTemplate:
        template = await self._repo.find_by_id(cmd.template_id, cmd.user_id)
        if template is None:
            raise RetroTemplateNotFoundException()

        if not template.is_default:
            # 커스텀 템플릿에는 reset 불가
            raise RetroTemplateDefaultNotDeletableException()

        template.content = DEFAULT_CONTENT[template.retro_type]
        template.updated_at = datetime.now(timezone.utc)
        return await self._repo.save(template)
