from datetime import datetime, timezone

from app.retrospective.application.dtos.template_commands import (
    CreateSummaryTemplateCommand,
)
from app.retrospective.domain.exceptions.exceptions import (
    SummaryTemplateLimitReachedException,
    SummaryTemplateNameDuplicatedException,
)
from app.retrospective.domain.models.summary_template import UserSummaryTemplate
from app.retrospective.domain.repositories.repository import (
    IUserSummaryTemplateRepository,
)
from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.config.retrospective import RetrospectiveConfig


class CreateSummaryTemplateUseCase:
    def __init__(
        self,
        repo: IUserSummaryTemplateRepository,
        config: RetrospectiveConfig,
    ) -> None:
        self._repo = repo
        self._config = config

    async def execute(
        self, cmd: CreateSummaryTemplateCommand
    ) -> UserSummaryTemplate:
        # 1. 같은 (user, type) 안 이름 중복 차단
        duplicate = await self._repo.find_by_name(
            cmd.user_id, cmd.summary_type, cmd.name
        )
        if duplicate is not None:
            raise SummaryTemplateNameDuplicatedException()

        # 2. 한도 검증
        count = await self._repo.count_by_user_and_type(cmd.user_id, cmd.summary_type)
        limit = self._config.summary_template_max_per_type
        if count >= limit:
            raise SummaryTemplateLimitReachedException(
                summary_type=cmd.summary_type.value, limit=limit
            )

        now = datetime.now(timezone.utc)
        template = UserSummaryTemplate(
            id=generate_id("tmpl"),
            user_id=cmd.user_id,
            summary_type=cmd.summary_type,
            name=cmd.name,
            content=cmd.content,
            created_at=now,
        )
        return await self._repo.save(template)
