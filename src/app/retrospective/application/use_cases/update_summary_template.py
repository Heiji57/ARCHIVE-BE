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

        # PATCH 부분 수정 — 전송된 필드(None 이 아닌)만 갱신.
        if cmd.name is not None and cmd.name != existing.name:
            # 이름이 바뀌면 (user, summary_type, new_name) 중복 차단
            duplicate = await self._repo.find_by_name(
                cmd.user_id, existing.summary_type, cmd.name
            )
            if duplicate is not None and duplicate.id != existing.id:
                raise SummaryTemplateNameDuplicatedException()
            existing.name = cmd.name

        if cmd.content is not None:
            existing.content = cmd.content

        existing.updated_at = datetime.now(timezone.utc)
        return await self._repo.save(existing)
