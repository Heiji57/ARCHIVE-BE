from datetime import datetime, timezone

from app.retrospective.application.dtos.folder_commands import MoveEntryToFolderCommand
from app.retrospective.domain.exceptions.exceptions import (
    FolderNotFoundException,
    JournalEntryNotFoundException,
    RetroSummaryNotFoundException,
)
from app.retrospective.domain.models.value_objects import RetroType, SummaryType
from app.retrospective.domain.repositories.repository import (
    IFolderRepository,
    IJournalEntryRepository,
    IRetroSummaryRepository,
)

# RetroType.YEARLY 는 SummaryType 명명(annual)과 다르다 — get_entries_page.py 와
# 동일한 정규화 관례.
_RETRO_TO_SUMMARY_TYPE = {
    RetroType.WEEKLY.value: SummaryType.WEEKLY,
    RetroType.MONTHLY.value: SummaryType.MONTHLY,
    RetroType.YEARLY.value: SummaryType.ANNUAL,
}


class MoveEntryToFolderUseCase:
    """PATCH /entries/:id/folder — 회고록을 다른 폴더로 이동(또는 폴더 해제).

    retroType 으로 daily(journal_entries)/weekly·monthly·yearly(retro_summaries)
    중 어느 테이블을 조회할지 라우팅한다 — 두 테이블 id 공간이 달라 retroType
    없이는 entry_id 만으로 어디 있는지 알 수 없다(paginated 컨벤션과 동일한 이유).
    """

    def __init__(
        self,
        entry_repo: IJournalEntryRepository,
        summary_repo: IRetroSummaryRepository,
        folder_repo: IFolderRepository,
    ) -> None:
        self._entry_repo = entry_repo
        self._summary_repo = summary_repo
        self._folder_repo = folder_repo

    async def execute(self, cmd: MoveEntryToFolderCommand) -> None:
        if cmd.folder_id is not None:
            folder = await self._folder_repo.find_by_id(cmd.folder_id, cmd.user_id)
            if folder is None:
                raise FolderNotFoundException()

        now = datetime.now(timezone.utc)

        if cmd.retro_type == RetroType.DAILY.value:
            entry = await self._entry_repo.find_by_id(cmd.entry_id, cmd.user_id)
            if entry is None:
                raise JournalEntryNotFoundException()
            entry.folder_id = cmd.folder_id
            entry.updated_at = now
            await self._entry_repo.save(entry)
            return

        summary_type = _RETRO_TO_SUMMARY_TYPE[cmd.retro_type]
        summary = await self._summary_repo.find_by_id(cmd.entry_id, cmd.user_id)
        if summary is None or summary.summary_type != summary_type:
            raise RetroSummaryNotFoundException()
        summary.folder_id = cmd.folder_id
        summary.updated_at = now
        await self._summary_repo.save(summary)
