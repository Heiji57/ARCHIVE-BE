from dataclasses import dataclass

from app.retrospective.application.dtos.folder_queries import GetFolderContentsQuery
from app.retrospective.domain.exceptions.exceptions import FolderNotFoundException
from app.retrospective.domain.models.folder import Folder
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import RetroType, SummaryType
from app.retrospective.domain.repositories.repository import (
    IFolderRepository,
    IJournalEntryRepository,
    IRetroSummaryRepository,
)
from app.retrospective.domain.utils.entry_ordering import merge_sorted_desc

_RETRO_TO_SUMMARY_TYPE = {
    RetroType.WEEKLY.value: SummaryType.WEEKLY,
    RetroType.MONTHLY.value: SummaryType.MONTHLY,
    RetroType.YEARLY.value: SummaryType.ANNUAL,
}


@dataclass(frozen=True)
class FolderWithCounts:
    folder: Folder
    folder_count: int
    entry_count: int


class GetFolderContentsUseCase:
    """GET /folders/contents — 폴더의 직계 하위 폴더 + 직계 회고록을 분리해서 반환.

    retroType 지정 시 그 타입만(daily=journal_entries, weekly/monthly/yearly=
    retro_summaries), 미지정 시 두 소스를 합쳐 최신순으로 정렬한 "전체" 뷰.
    폴더는 사용자가 직접 분류해 넣은 하위 집합이라(전체 이력이 아님) 정렬 후
    애플리케이션 레벨에서 페이지 슬라이스해도 이 앱 스케일에서는 문제 없다.
    """

    def __init__(
        self,
        folder_repo: IFolderRepository,
        entry_repo: IJournalEntryRepository,
        summary_repo: IRetroSummaryRepository,
    ) -> None:
        self._folder_repo = folder_repo
        self._entry_repo = entry_repo
        self._summary_repo = summary_repo

    async def execute(
        self, query: GetFolderContentsQuery
    ) -> tuple[list[FolderWithCounts], list[JournalEntry | RetroSummary], int]:
        if query.folder_id is not None:
            folder = await self._folder_repo.find_by_id(query.folder_id, query.user_id)
            if folder is None:
                raise FolderNotFoundException()

        subfolders = await self._folder_repo.find_children(query.user_id, query.folder_id)
        subfolder_ids = [f.id for f in subfolders]
        folder_counts = await self._folder_repo.count_children_by_parent_ids(
            query.user_id, subfolder_ids
        )
        entry_counts = await self._entry_repo.count_by_folder_ids(query.user_id, subfolder_ids)
        summary_counts = await self._summary_repo.count_by_folder_ids(query.user_id, subfolder_ids)
        subfolders_with_counts = [
            FolderWithCounts(
                folder=f,
                folder_count=folder_counts.get(f.id, 0),
                entry_count=entry_counts.get(f.id, 0) + summary_counts.get(f.id, 0),
            )
            for f in subfolders
        ]

        items: list[JournalEntry | RetroSummary]
        if query.retro_type:
            if query.retro_type == RetroType.DAILY.value:
                items = list(
                    await self._entry_repo.find_by_folder(
                        query.user_id, query.folder_id, query.retro_type
                    )
                )
            else:
                summary_type = _RETRO_TO_SUMMARY_TYPE[query.retro_type]
                items = list(
                    await self._summary_repo.find_by_folder(
                        query.user_id, query.folder_id, summary_type
                    )
                )
        else:
            entries = await self._entry_repo.find_by_folder(query.user_id, query.folder_id)
            summaries = await self._summary_repo.find_by_folder(query.user_id, query.folder_id)
            items = merge_sorted_desc(entries, summaries)

        total = len(items)
        start = (query.page - 1) * query.size
        page_items = items[start : start + query.size]
        return subfolders_with_counts, page_items, total
