from app.retrospective.application.dtos.summary_commands import EditSummaryCommand
from app.retrospective.domain.exceptions.exceptions import RetroSummaryNotFoundException
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.repositories.repository import IRetroSummaryRepository


class EditSummaryUseCase:
    """요약 마크다운 오버라이드 저장/해제.

    content_markdown 이 문자열이면 편집본 저장, None 이면 편집 해제(AI 원본 복귀).
    AI 원본(content.sections)은 건드리지 않는다.
    """

    def __init__(self, summary_repo: IRetroSummaryRepository) -> None:
        self._summary_repo = summary_repo

    async def execute(self, cmd: EditSummaryCommand) -> RetroSummary:
        summary = await self._summary_repo.find_by_id(cmd.summary_id, cmd.user_id)
        if not summary:
            raise RetroSummaryNotFoundException()
        summary.apply_edit(cmd.content_markdown)
        return await self._summary_repo.save(summary)
