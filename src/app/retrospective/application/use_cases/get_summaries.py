from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.domain.repositories.repository import IRetroSummaryRepository


class GetSummariesUseCase:
    def __init__(self, summary_repo: IRetroSummaryRepository) -> None:
        self._summary_repo = summary_repo

    async def execute(self, user_id: str, summary_type: SummaryType) -> list[RetroSummary]:
        return await self._summary_repo.find_all_by_type(user_id, summary_type)
