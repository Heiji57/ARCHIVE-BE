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
from app.retrospective.domain.utils.entry_ordering import merge_sorted_desc_with_id

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

    page/size 는 폴더와 회고록을 합친 **하나의 시퀀스**에 대한 오프셋이다:

        seq = [폴더: name ASC, id ASC] ++ [회고록: 날짜 DESC, id DESC]

    폴더 블록이 먼저 소진된 뒤 회고록이 이어진다(파일 탐색기 방식). 응답
    구조(folders/entries 분리)는 그대로지만 folders 는 "직계 하위 폴더 전부"가
    아니라 이 페이지 구간에 걸친 조각이고, total 은 폴더 총개수 + 회고록
    총건수다. retroType 은 회고록에만 걸리므로 folderTotal 은 탭과 무관하다.
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

        offset = (query.page - 1) * query.size
        folder_total = await self._folder_repo.count_children(query.user_id, query.folder_id)
        entry_total = await self._count_entries(query)

        subfolders = await self._folder_repo.find_children_page(
            query.user_id, query.folder_id, offset, query.size
        )
        subfolders_with_counts = await self._with_counts(query.user_id, subfolders)

        # 폴더가 쓰고 남은 칸만 회고록으로 채운다. offset 이 폴더 블록을 넘어선
        # 만큼이 회고록 시퀀스 안에서의 오프셋이 된다.
        remaining = query.size - len(subfolders)
        entry_offset = max(0, offset - folder_total)
        items = (
            await self._fetch_entries(query, entry_offset, remaining) if remaining > 0 else []
        )

        return subfolders_with_counts, items, folder_total + entry_total

    async def _with_counts(
        self, user_id: str, subfolders: list[Folder]
    ) -> list[FolderWithCounts]:
        subfolder_ids = [f.id for f in subfolders]
        folder_counts = await self._folder_repo.count_children_by_parent_ids(
            user_id, subfolder_ids
        )
        entry_counts = await self._entry_repo.count_by_folder_ids(user_id, subfolder_ids)
        summary_counts = await self._summary_repo.count_by_folder_ids(user_id, subfolder_ids)
        return [
            FolderWithCounts(
                folder=f,
                folder_count=folder_counts.get(f.id, 0),
                entry_count=entry_counts.get(f.id, 0) + summary_counts.get(f.id, 0),
            )
            for f in subfolders
        ]

    async def _count_entries(self, query: GetFolderContentsQuery) -> int:
        if query.retro_type == RetroType.DAILY.value:
            return await self._entry_repo.count_by_folder(
                query.user_id, query.folder_id, query.retro_type
            )
        if query.retro_type:
            return await self._summary_repo.count_by_folder(
                query.user_id, query.folder_id, _RETRO_TO_SUMMARY_TYPE[query.retro_type]
            )
        return await self._entry_repo.count_by_folder(
            query.user_id, query.folder_id
        ) + await self._summary_repo.count_by_folder(query.user_id, query.folder_id)

    async def _fetch_entries(
        self, query: GetFolderContentsQuery, offset: int, limit: int
    ) -> list[JournalEntry | RetroSummary]:
        if query.retro_type == RetroType.DAILY.value:
            return list(
                await self._entry_repo.find_by_folder_page(
                    query.user_id, query.folder_id, query.retro_type, offset, limit
                )
            )
        if query.retro_type:
            return list(
                await self._summary_repo.find_by_folder_page(
                    query.user_id,
                    query.folder_id,
                    _RETRO_TO_SUMMARY_TYPE[query.retro_type],
                    offset,
                    limit,
                )
            )

        # "전체" 뷰 — 두 소스를 합친 시퀀스의 [offset, offset+limit) 구간이 필요하다.
        # 각 소스에서 상위 (offset+limit) 개씩만 가져오면 합친 시퀀스의 상위
        # (offset+limit) 개를 항상 커버한다(어느 한쪽이 그 구간을 전부 차지해도
        # 그 개수를 넘을 수 없으므로). 두 소스를 각각 정렬해 이어붙이는 게 아니라
        # 합친 뒤 전체에 (날짜 DESC, id DESC) 를 다시 건다.
        fetch_size = offset + limit
        entries = await self._entry_repo.find_by_folder_page(
            query.user_id, query.folder_id, None, 0, fetch_size
        )
        summaries = await self._summary_repo.find_by_folder_page(
            query.user_id, query.folder_id, None, 0, fetch_size
        )
        merged = merge_sorted_desc_with_id(entries, summaries)
        return merged[offset : offset + limit]
