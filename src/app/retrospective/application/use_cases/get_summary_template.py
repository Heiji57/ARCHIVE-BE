from app.retrospective.domain.exceptions.exceptions import (
    SummaryTemplateNotFoundException,
)
from app.retrospective.domain.models.summary_template import UserSummaryTemplate
from app.retrospective.domain.repositories.repository import (
    IUserSummaryTemplateRepository,
)


class GetSummaryTemplateUseCase:
    def __init__(self, repo: IUserSummaryTemplateRepository) -> None:
        self._repo = repo

    async def execute(
        self, template_id: str, user_id: str
    ) -> UserSummaryTemplate:
        template = await self._repo.find_by_id(template_id, user_id)
        if template is None:
            raise SummaryTemplateNotFoundException()
        return template
