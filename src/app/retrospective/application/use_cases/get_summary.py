from app.retrospective.domain.exceptions.exceptions import RetroSummaryNotFoundException
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.repositories.repository import IRetroSummaryRepository


class GetSummaryUseCase:
    def __init__(self, summary_repo: IRetroSummaryRepository) -> None:
        self._summary_repo = summary_repo

    async def execute(self, summary_id: str, user_id: str) -> RetroSummary:
        summary = await self._summary_repo.find_by_id(summary_id, user_id)
        if not summary:
            raise RetroSummaryNotFoundException()
        return summary
