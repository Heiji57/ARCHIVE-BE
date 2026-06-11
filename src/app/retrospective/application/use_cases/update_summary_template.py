from datetime import datetime, timezone

from app.retrospective.application.dtos.template_commands import (
    UpdateSummaryTemplateCommand,
)
from app.retrospective.domain.exceptions.exceptions import (
    SummaryTemplateNameDuplicatedException,
    SummaryTemplateNotFoundException,
)
from app.retrospective.domain.models.summary_template import UserSummaryTemplate
from app.retrospective.domain.repositories.repository import (
    IUserSummaryTemplateRepository,
)


class UpdateSummaryTemplateUseCase:
    def __init__(self, repo: IUserSummaryTemplateRepository) -> None:
        self._repo = repo

    async def execute(
        self, cmd: UpdateSummaryTemplateCommand
    ) -> UserSummaryTemplate:
        existing = await self._repo.find_by_id(cmd.template_id, cmd.user_id)
        if existing is None:
            raise SummaryTemplateNotFoundException()

        # 이름이 바뀌면 (user, summary_type, new_name) 중복 차단
        if cmd.name != existing.name:
            duplicate = await self._repo.find_by_name(
                cmd.user_id, existing.summary_type, cmd.name
            )
            if duplicate is not None and duplicate.id != existing.id:
                raise SummaryTemplateNameDuplicatedException()

        existing.name = cmd.name
        existing.content = cmd.content
        existing.updated_at = datetime.now(timezone.utc)
        return await self._repo.save(existing)
