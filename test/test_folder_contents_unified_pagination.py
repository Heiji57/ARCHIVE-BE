"""
GET /folders/contents 통합 페이지네이션(폴더 + 회고록 단일 시퀀스) 오프셋 계산 검증.

    seq = [폴더: name ASC, id ASC] ++ [회고록: 날짜 DESC, id DESC]

page/size 는 이 seq 의 오프셋이고 total = 폴더 총개수 + 회고록 총건수다.
스펙 문서 "확인해야 할 경계 케이스" 표의 케이스들을 그대로 옮겼다.

이 저장소엔 pytest 가 아직 설치/선언돼 있지 않아(requirements.txt 미포함),
test_update_todo_following_scope.py 와 동일하게 직접 실행 가능한 스크립트로 작성한다.
pytest 가 나중에 추가되면 async def test_* 함수들이 그대로 수집된다.

실행:
    python test/test_folder_contents_unified_pagination.py
"""
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone

from app.retrospective.application.dtos.folder_queries import GetFolderContentsQuery
from app.retrospective.application.use_cases.get_folder_contents import (
    GetFolderContentsUseCase,
)
from app.retrospective.domain.models.folder import Folder
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import (
    RetroType,
    SummaryStatus,
    SummaryType,
)

_NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)
_USER = "user_1"


# ── fakes — SQL 의 정렬/offset/limit 의미를 그대로 흉내낸다 ─────────────────


class FakeFolderRepo:
    def __init__(self, folders: list[Folder]) -> None:
        self.folders = folders

    def _children(self, user_id: str, parent_folder_id: str | None) -> list[Folder]:
        rows = [
            f
            for f in self.folders
            if f.user_id == user_id and f.parent_folder_id == parent_folder_id
        ]
        return sorted(rows, key=lambda f: (f.name, f.id))  # name ASC, id ASC

    async def find_by_id(self, id: str, user_id: str) -> Folder | None:
        return next((f for f in self.folders if f.id == id and f.user_id == user_id), None)

    async def find_children_page(
        self, user_id: str, parent_folder_id: str | None, offset: int, limit: int
    ) -> list[Folder]:
        if limit <= 0:
            return []
        return self._children(user_id, parent_folder_id)[offset : offset + limit]

    async def count_children(self, user_id: str, parent_folder_id: str | None) -> int:
        return len(self._children(user_id, parent_folder_id))

    async def count_children_by_parent_ids(
        self, user_id: str, parent_ids: list[str]
    ) -> dict[str, int]:
        return {}


class FakeEntryRepo:
    def __init__(self, entries: list[JournalEntry]) -> None:
        self.entries = entries

    def _scope(
        self, user_id: str, folder_id: str | None, retro_type: str | None
    ) -> list[JournalEntry]:
        rows = [
            e
            for e in self.entries
            if e.user_id == user_id
            and e.folder_id == folder_id
            and (retro_type is None or e.retro_type.value == retro_type)
        ]
        # date_key DESC, id DESC
        return sorted(rows, key=lambda e: (e.date_key, e.id), reverse=True)

    async def find_by_folder_page(
        self,
        user_id: str,
        folder_id: str | None,
        retro_type: str | None,
        offset: int,
        limit: int,
    ) -> list[JournalEntry]:
        if limit <= 0:
            return []
        return self._scope(user_id, folder_id, retro_type)[offset : offset + limit]

    async def count_by_folder(
        self, user_id: str, folder_id: str | None, retro_type: str | None = None
    ) -> int:
        return len(self._scope(user_id, folder_id, retro_type))

    async def count_by_folder_ids(self, user_id: str, folder_ids: list[str]) -> dict[str, int]:
        return {}


class FakeSummaryRepo:
    def __init__(self, summaries: list[RetroSummary]) -> None:
        self.summaries = summaries

    def _scope(
        self, user_id: str, folder_id: str | None, summary_type: SummaryType | None
    ) -> list[RetroSummary]:
        rows = [
            s
            for s in self.summaries
            if s.user_id == user_id
            and s.folder_id == folder_id
            and (summary_type is None or s.summary_type == summary_type)
        ]
        # period_start DESC, id DESC
        return sorted(rows, key=lambda s: (s.period_start, s.id), reverse=True)

    async def find_by_folder_page(
        self,
        user_id: str,
        folder_id: str | None,
        summary_type: SummaryType | None,
        offset: int,
        limit: int,
    ) -> list[RetroSummary]:
        if limit <= 0:
            return []
        return self._scope(user_id, folder_id, summary_type)[offset : offset + limit]

    async def count_by_folder(
        self, user_id: str, folder_id: str | None, summary_type: SummaryType | None = None
    ) -> int:
        return len(self._scope(user_id, folder_id, summary_type))

    async def count_by_folder_ids(self, user_id: str, folder_ids: list[str]) -> dict[str, int]:
        return {}


# ── seed helpers ───────────────────────────────────────────────────────────


def _folders(n: int, parent: str | None = None) -> list[Folder]:
    return [
        Folder(
            id=f"folder_{i:03d}",
            user_id=_USER,
            name=f"folder-{i:03d}",
            parent_folder_id=parent,
            created_at=_NOW,
        )
        for i in range(n)
    ]


def _entries(n: int, folder_id: str | None = None) -> list[JournalEntry]:
    """date_key 는 최신 → 과거 순으로 하루씩 내려간다(i=0 이 가장 최신)."""
    return [
        JournalEntry(
            id=f"entry_{i:03d}",
            user_id=_USER,
            date_key=(date(2026, 9, 6) - timedelta(days=i)).isoformat(),
            title=f"entry-{i:03d}",
            content="",
            retro_type=RetroType.DAILY,
            folder_id=folder_id,
            created_at=_NOW,
        )
        for i in range(n)
    ]


def _summaries(n: int, folder_id: str | None = None) -> list[RetroSummary]:
    return [
        RetroSummary(
            id=f"summary_{i:03d}",
            user_id=_USER,
            summary_type=SummaryType.WEEKLY,
            period_start=date(2026, 9, 6) - timedelta(days=i),
            period_end=date(2026, 9, 6) - timedelta(days=i),
            status=SummaryStatus.COMPLETED,
            content=None,
            folder_id=folder_id,
            created_at=_NOW,
        )
        for i in range(n)
    ]


def _use_case(
    folders: list[Folder],
    entries: list[JournalEntry],
    summaries: list[RetroSummary] | None = None,
) -> GetFolderContentsUseCase:
    return GetFolderContentsUseCase(
        FakeFolderRepo(folders),  # type: ignore[arg-type]
        FakeEntryRepo(entries),  # type: ignore[arg-type]
        FakeSummaryRepo(summaries or []),  # type: ignore[arg-type]
    )


async def _page(
    use_case: GetFolderContentsUseCase,
    page: int,
    size: int,
    retro_type: str | None = None,
) -> tuple[int, int, int]:
    """(폴더 수, 회고록 수, total) 로 축약."""
    folders, items, total = await use_case.execute(
        GetFolderContentsQuery(
            user_id=_USER, folder_id=None, retro_type=retro_type, page=page, size=size
        )
    )
    return len(folders), len(items), total


# ── tests ──────────────────────────────────────────────────────────────────


async def test_spec_example_25_folders_100_entries_size_20():
    """스펙 §3-4 검산표 — 폴더 25 · 회고록 100 · size 20 → 총 7페이지, total 125."""
    uc = _use_case(_folders(25), _entries(100))
    expected = [
        (1, 20, 0),
        (2, 5, 15),
        (3, 0, 20),
        (4, 0, 20),
        (5, 0, 20),
        (6, 0, 20),
        (7, 0, 5),
    ]
    for page, want_folders, want_entries in expected:
        got_folders, got_entries, total = await _page(uc, page, 20)
        assert (got_folders, got_entries) == (want_folders, want_entries), (
            f"page {page}: {(got_folders, got_entries)} != {(want_folders, want_entries)}"
        )
        assert total == 125, f"page {page}: total {total} != 125"


async def test_no_folders_behaves_like_entries_only():
    """폴더 0개 → 기존 동작과 동일(1페이지부터 회고록, total = 회고록 건수)."""
    uc = _use_case([], _entries(35))
    assert await _page(uc, 1, 10) == (0, 10, 35)
    assert await _page(uc, 4, 10) == (0, 5, 35)


async def test_folders_exact_multiple_of_size():
    """폴더가 size 의 정확한 배수 → 2페이지는 폴더 0 + 회고록 20 (경계에서 정상)."""
    uc = _use_case(_folders(20), _entries(20))
    assert await _page(uc, 1, 20) == (20, 0, 40)
    assert await _page(uc, 2, 20) == (0, 20, 40)


async def test_folders_only_no_entries():
    """폴더만 25개, 회고록 0건 → total 25, 2페이지 = 폴더 5 + 회고록 0, 총 2페이지."""
    uc = _use_case(_folders(25), [])
    assert await _page(uc, 1, 20) == (20, 0, 25)
    assert await _page(uc, 2, 20) == (5, 0, 25)
    assert await _page(uc, 3, 20) == (0, 0, 25)


async def test_empty_folder_is_not_an_error():
    """폴더 0 · 회고록 0 → total 0, 두 배열 모두 빈 배열(에러 아님)."""
    uc = _use_case([], [])
    assert await _page(uc, 1, 10) == (0, 0, 0)


async def test_page_beyond_last_returns_empty_with_correct_total():
    """마지막 페이지 초과 → 두 배열 모두 비지만 total 은 정상값."""
    uc = _use_case(_folders(3), _entries(5))
    assert await _page(uc, 99, 10) == (0, 0, 8)


async def test_last_page_is_partial():
    """마지막 페이지는 len(folders) + len(entries) < size."""
    uc = _use_case(_folders(3), _entries(5))
    folders, entries, total = await _page(uc, 1, 10)
    assert (folders, entries, total) == (3, 5, 8)
    assert folders + entries < 10


async def test_retro_type_switch_keeps_folder_total():
    """retroType 전환 → folderTotal 불변, entryTotal 만 변한다."""
    uc = _use_case(_folders(5), _entries(10), _summaries(3))
    # 전체 뷰: 폴더 5 + (daily 10 + weekly 3) = 18
    assert await _page(uc, 1, 10) == (5, 5, 18)
    # daily 만: 폴더 5 + daily 10 = 15
    assert await _page(uc, 1, 10, RetroType.DAILY.value) == (5, 5, 15)
    # weekly 만: 폴더 5 + weekly 3 = 8
    assert await _page(uc, 1, 10, RetroType.WEEKLY.value) == (5, 3, 8)


async def test_999_folders_page_one_carries_only_size_folders():
    """폴더 999개여도 1페이지에는 size 개만 실린다(전부가 아니라)."""
    uc = _use_case(_folders(999), _entries(20))
    assert await _page(uc, 1, 10) == (10, 0, 1019)


async def test_merged_view_pages_are_disjoint_and_complete():
    """"전체" 뷰(daily + weekly 합산)에서 같은 날짜가 겹쳐도 페이지 경계에서
    누락/중복이 없어야 한다 — UNION 전체에 (날짜 DESC, id DESC) 를 걸기 때문."""
    # date_key 와 period_start 가 완전히 겹치는 20 + 20 건
    uc = _use_case(_folders(3), _entries(20), _summaries(20))
    seen: list[str] = []
    for page in range(1, 6):  # 3 + 40 = 43건 → size 10 이면 5페이지
        folders, items, total = await uc.execute(
            GetFolderContentsQuery(user_id=_USER, folder_id=None, page=page, size=10)
        )
        assert total == 43
        seen.extend(i.id for i in items)
    assert len(seen) == 40, f"수집된 회고록 {len(seen)}건 != 40건"
    assert len(set(seen)) == 40, "페이지 경계에서 중복 발생"

    # 전체를 한 번에 받은 순서와 페이지를 이어붙인 순서가 같아야 한다
    _, all_items, _ = await uc.execute(
        GetFolderContentsQuery(user_id=_USER, folder_id=None, page=1, size=50)
    )
    assert [i.id for i in all_items] == seen


async def test_missing_folder_raises():
    """존재하지 않는 folderId 는 그대로 FolderNotFoundException."""
    from app.retrospective.domain.exceptions.exceptions import FolderNotFoundException

    uc = _use_case(_folders(3), _entries(3))
    try:
        await uc.execute(
            GetFolderContentsQuery(user_id=_USER, folder_id="folder_nope", page=1, size=10)
        )
    except FolderNotFoundException:
        return
    raise AssertionError("FolderNotFoundException 이 발생하지 않았다")


_TESTS = [
    test_spec_example_25_folders_100_entries_size_20,
    test_no_folders_behaves_like_entries_only,
    test_folders_exact_multiple_of_size,
    test_folders_only_no_entries,
    test_empty_folder_is_not_an_error,
    test_page_beyond_last_returns_empty_with_correct_total,
    test_last_page_is_partial,
    test_retro_type_switch_keeps_folder_total,
    test_999_folders_page_one_carries_only_size_folders,
    test_merged_view_pages_are_disjoint_and_complete,
    test_missing_folder_raises,
]


async def _run_all() -> bool:
    ok = True
    for fn in _TESTS:
        try:
            await fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            ok = False
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 — 스크립트 러너, 실패 원인 그대로 노출
            ok = False
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    return ok


if __name__ == "__main__":
    passed = asyncio.run(_run_all())
    sys.exit(0 if passed else 1)
