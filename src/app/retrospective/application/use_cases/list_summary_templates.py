from app.retrospective.domain.models.summary_template import UserSummaryTemplate
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.domain.repositories.repository import (
    IUserSummaryTemplateRepository,
)


class ListSummaryTemplatesUseCase:
    def __init__(self, repo: IUserSummaryTemplateRepository) -> None:
        self._repo = repo

    async def execute(
        self, user_id: str, summary_type: SummaryType
    ) -> list[UserSummaryTemplate]:
        return await self._repo.find_by_user_and_type(user_id, summary_type)
