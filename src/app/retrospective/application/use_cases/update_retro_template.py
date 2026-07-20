from datetime import datetime, timezone

from app.retrospective.application.dtos.retro_template_commands import UpdateRetroTemplateCommand
from app.retrospective.domain.exceptions.exceptions import (
    RetroTemplateNameDuplicatedException,
    RetroTemplateNotFoundException,
)
from app.retrospective.domain.models.retro_template import RetroTemplate
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository


class UpdateRetroTemplateUseCase:
    def __init__(self, repo: IRetroTemplateRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: UpdateRetroTemplateCommand) -> RetroTemplate:
        template = await self._repo.find_by_id(cmd.template_id, cmd.user_id)
        if template is None:
            raise RetroTemplateNotFoundException()

        if cmd.name is not None and cmd.name != template.name:
            duplicate = await self._repo.find_by_name(
                cmd.user_id, template.retro_type, cmd.name
            )
            if duplicate is not None:
                raise RetroTemplateNameDuplicatedException()
            template.name = cmd.name

        if cmd.content is not None:
            template.content = cmd.content

        template.updated_at = datetime.now(timezone.utc)
        return await self._repo.save(template)
