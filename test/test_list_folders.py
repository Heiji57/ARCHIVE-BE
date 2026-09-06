"""
GET /folders — 전체 폴더 평평한 목록 검증.

용도는 경로 조립(id → 이름 → 조상 사슬)이라 depth 무관 전체 집합을 name ASC,
id ASC 로 돌려주고, 페이지네이션 대신 MAX_FOLDERS 상한만 둔다.
백엔드 요청서 "확인해야 할 경계 케이스" 표의 케이스들을 그대로 옮겼다.

이 저장소엔 pytest 가 아직 설치/선언돼 있지 않아(requirements.txt 미포함),
test_folder_contents_unified_pagination.py 와 동일하게 직접 실행 가능한
스크립트로 작성한다. pytest 가 나중에 추가되면 async def test_* 가 그대로 수집된다.

실행:
    PYTHONPATH=src python test/test_list_folders.py
"""
import asyncio
import sys
from datetime import datetime, timezone

from app.retrospective.application.use_cases.list_folders import (
    MAX_FOLDERS,
    ListFoldersUseCase,
)
from app.retrospective.domain.models.folder import Folder
from app.retrospective.presentation.responses.folder_responses import (
    FolderListResponse,
    FolderSummaryResponse,
)

_NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)
_USER = "user_1"


class FakeFolderRepo:
    """find_all 의 SQL 의미(user 스코프, name ASC/id ASC, LIMIT)를 흉내낸다."""

    def __init__(self, folders: list[Folder]) -> None:
        self.folders = folders

    async def find_all(self, user_id: str, limit: int) -> list[Folder]:
        if limit <= 0:
            return []
        rows = [f for f in self.folders if f.user_id == user_id]
        rows.sort(key=lambda f: (f.name, f.id))
        return rows[:limit]


def _folder(fid: str, name: str, parent: str | None = None, user: str = _USER) -> Folder:
    return Folder(
        id=fid, user_id=user, name=name, parent_folder_id=parent, created_at=_NOW
    )


def _use_case(folders: list[Folder]) -> ListFoldersUseCase:
    return ListFoldersUseCase(FakeFolderRepo(folders))  # type: ignore[arg-type]


# ── 경계 케이스 ────────────────────────────────────────────────────────────


async def test_no_folders_returns_empty_list() -> None:
    got = await _use_case([]).execute(_USER)
    assert got == [], got


async def test_root_only_folders_all_have_null_parent() -> None:
    got = await _use_case([_folder("f2", "B"), _folder("f1", "A")]).execute(_USER)
    assert [f.name for f in got] == ["A", "B"], got
    assert all(f.parent_folder_id is None for f in got), got


async def test_deeply_nested_folders_are_flat_not_a_tree() -> None:
    """모든 depth 가 한 배열에 평평하게 담겨야 한다(트리로 감싸지 않는다)."""
    folders = [
        _folder("f1", "A"),
        _folder("f2", "B", parent="f1"),
        _folder("f3", "C", parent="f2"),
        _folder("f4", "D", parent="f3"),
    ]
    got = await _use_case(folders).execute(_USER)
    assert len(got) == 4, got
    assert [f.id for f in got] == ["f1", "f2", "f3", "f4"], got
    # 조상 사슬이 배열 안에서 온전히 풀린다 — 경로 조립이 성립하는 조건.
    by_id = {f.id: f for f in got}
    cursor, chain = "f4", []
    while cursor is not None:
        chain.append(by_id[cursor].name)
        cursor = by_id[cursor].parent_folder_id
    assert chain == ["D", "C", "B", "A"], chain


async def test_other_users_folders_are_excluded() -> None:
    folders = [_folder("f1", "A"), _folder("f9", "Z", user="user_2")]
    got = await _use_case(folders).execute(_USER)
    assert [f.id for f in got] == ["f1"], got


async def test_sorted_by_name_then_id() -> None:
    folders = [
        _folder("f3", "같은이름"),
        _folder("f1", "같은이름"),
        _folder("f2", "가나다"),
    ]
    got = await _use_case(folders).execute(_USER)
    assert [f.id for f in got] == ["f2", "f1", "f3"], got


async def test_result_is_capped_at_max_folders() -> None:
    folders = [_folder(f"f{i:05d}", f"folder {i:05d}") for i in range(MAX_FOLDERS + 500)]
    got = await _use_case(folders).execute(_USER)
    assert len(got) == MAX_FOLDERS, len(got)


# ── 응답 스키마 ────────────────────────────────────────────────────────────


async def test_response_carries_only_three_fields_in_camel_case() -> None:
    """뱃지용 개수·타임스탬프를 담지 않는 것이 이 엔드포인트의 요점이다 —
    전체 폴더에 집계를 걸지 않기 위해서다."""
    payload = FolderListResponse(
        folders=[FolderSummaryResponse.from_entity(_folder("f2", "1분기", parent="f1"))]
    ).model_dump(by_alias=True)
    assert payload == {
        "folders": [{"id": "f2", "name": "1분기", "parentFolderId": "f1"}]
    }, payload


async def test_root_folder_serializes_parent_as_null() -> None:
    payload = FolderSummaryResponse.from_entity(_folder("f1", "A")).model_dump(
        by_alias=True
    )
    assert payload["parentFolderId"] is None, payload


_TESTS = [
    test_no_folders_returns_empty_list,
    test_root_only_folders_all_have_null_parent,
    test_deeply_nested_folders_are_flat_not_a_tree,
    test_other_users_folders_are_excluded,
    test_sorted_by_name_then_id,
    test_result_is_capped_at_max_folders,
    test_response_carries_only_three_fields_in_camel_case,
    test_root_folder_serializes_parent_as_null,
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
