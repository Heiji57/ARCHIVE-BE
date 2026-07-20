from datetime import datetime, timezone

from app.retrospective.application.dtos.retro_template_commands import CreateRetroTemplateCommand
from app.retrospective.domain.exceptions.exceptions import RetroTemplateNameDuplicatedException
from app.retrospective.domain.models.retro_template import RetroTemplate
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository
from app.shared.domain.utils.id import generate_id


class CreateRetroTemplateUseCase:
    def __init__(self, repo: IRetroTemplateRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: CreateRetroTemplateCommand) -> RetroTemplate:
        duplicate = await self._repo.find_by_name(cmd.user_id, cmd.retro_type, cmd.name)
        if duplicate is not None:
            raise RetroTemplateNameDuplicatedException()

        now = datetime.now(timezone.utc)
        template = RetroTemplate(
            id=generate_id("tmpl"),
            user_id=cmd.user_id,
            retro_type=cmd.retro_type,
            name=cmd.name,
            content=cmd.content,
            is_default=False,
            created_at=now,
        )
        return await self._repo.save(template)
