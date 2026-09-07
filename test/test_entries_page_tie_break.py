"""
GET /entries/paginated "전체" 뷰의 페이지 경계 결정성 검증.

daily(journal_entries)와 weekly/monthly/annual(retro_summaries)를 합치는 "전체"
뷰는 각 소스에서 상위 (page*size) 개를 가져와 애플리케이션에서 병합한다. 이
top-K 트릭은 **소스 정렬과 병합 정렬의 기준이 같을 때만** 성립한다 — 기준이
어긋나거나 동률에서 순서가 비결정적이면 페이지 경계에서 항목이 누락되거나
중복된다.

같은 date_key/period_start 가 여러 건 나오는 것은 예외가 아니라 일상이다:
하루에 daily 1건 + 그 주의 weekly + 그 달의 monthly 가 같은 날짜를 가질 수 있고,
백필하면 같은 날짜의 항목이 무더기로 생긴다.

이 저장소엔 pytest 가 아직 설치/선언돼 있지 않아(requirements.txt 미포함),
다른 테스트들과 동일하게 직접 실행 가능한 스크립트로 작성한다.

실행:
    PYTHONPATH=src python test/test_entries_page_tie_break.py
"""
import asyncio
import sys
from datetime import date, datetime, timezone

from app.retrospective.application.dtos.queries import GetEntriesPageQuery
from app.retrospective.application.use_cases.get_entries_page import (
    GetEntriesPageUseCase,
)
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import (
    RetroType,
    SummaryStatus,
    SummaryType,
)
from app.retrospective.domain.utils.entry_ordering import content_order_key

_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)
_USER = "user_1"
_SAME_DAY = "2026-06-15"


# ── fakes — find_page 의 SQL 의미(ORDER BY 날짜 DESC, id DESC + offset/limit) ──


class FakeEntryRepo:
    def __init__(self, rows: list[JournalEntry]) -> None:
        self.rows = rows

    async def find_page(self, user_id, retro_type, page, size, q, from_d, to_d):
        rows = sorted(
            [r for r in self.rows if r.user_id == user_id],
            key=lambda r: (r.date_key, r.id),
            reverse=True,
        )
        start = (page - 1) * size
        return rows[start : start + size], len(rows)


class FakeSummaryRepo:
    def __init__(self, rows: list[RetroSummary]) -> None:
        self.rows = rows

    async def find_page(self, user_id, summary_type, page, size, q, from_d, to_d):
        rows = sorted(
            [r for r in self.rows if r.user_id == user_id],
            key=lambda r: (r.period_start, r.id),
            reverse=True,
        )
        start = (page - 1) * size
        return rows[start : start + size], len(rows)


def _entry(eid: str, date_key: str = _SAME_DAY) -> JournalEntry:
    return JournalEntry(
        id=eid,
        user_id=_USER,
        date_key=date_key,
        title=eid,
        content="",
        retro_type=RetroType.DAILY,
        created_at=_NOW,
    )


def _summary(sid: str, start: str = _SAME_DAY) -> RetroSummary:
    d = date.fromisoformat(start)
    return RetroSummary(
        id=sid,
        user_id=_USER,
        summary_type=SummaryType.WEEKLY,
        period_start=d,
        period_end=d,
        status=SummaryStatus.COMPLETED,
        content=None,
        created_at=_NOW,
    )


def _use_case(entries, summaries) -> GetEntriesPageUseCase:
    return GetEntriesPageUseCase(  # type: ignore[arg-type]
        FakeEntryRepo(entries), FakeSummaryRepo(summaries)
    )


async def _walk_pages(uc, size: int, total: int) -> list[str]:
    """페이지를 끝까지 넘기며 나온 id 를 순서대로 모은다."""
    seen: list[str] = []
    pages = (total + size - 1) // size
    for page in range(1, pages + 1):
        items, reported_total = await uc.execute(
            GetEntriesPageQuery(
                user_id=_USER, retro_type=None, page=page, size=size, q=None
            )
        )
        assert reported_total == total, f"total {reported_total} != {total}"
        seen.extend(i.id for i in items)
    return seen


# ── 테스트 ────────────────────────────────────────────────────────────────


async def test_all_same_date_pages_are_disjoint_and_complete() -> None:
    """날짜가 전부 동일한 최악의 경우 — id tie-break 가 없으면 여기서 깨진다."""
    entries = [_entry(f"entry_{i:03d}") for i in range(20)]
    summaries = [_summary(f"summary_{i:03d}") for i in range(20)]
    seen = await _walk_pages(_use_case(entries, summaries), size=7, total=40)

    assert len(seen) == 40, len(seen)
    assert len(set(seen)) == 40, f"중복 발생: {len(seen) - len(set(seen))}건"
    expected = [
        i.id for i in sorted([*entries, *summaries], key=content_order_key, reverse=True)
    ]
    assert seen == expected, "페이지를 이어붙인 순서가 전역 정렬과 다르다"


async def test_mixed_dates_with_ties_stay_stable() -> None:
    """같은 날짜 묶음이 여러 개 섞인 현실적인 경우."""
    entries, summaries = [], []
    for day in ("2026-06-15", "2026-06-14", "2026-06-13"):
        for i in range(4):
            entries.append(_entry(f"entry_{day}_{i}", day))
            summaries.append(_summary(f"summary_{day}_{i}", day))
    seen = await _walk_pages(_use_case(entries, summaries), size=5, total=24)

    assert len(set(seen)) == 24, f"누락/중복: {sorted(set(seen)) != sorted(seen)}"
    expected = [
        i.id for i in sorted([*entries, *summaries], key=content_order_key, reverse=True)
    ]
    assert seen == expected, "페이지를 이어붙인 순서가 전역 정렬과 다르다"


async def test_one_source_dominates_top_k() -> None:
    """한쪽 소스가 상위 구간을 독점해도 top-K 트릭이 성립해야 한다."""
    entries = [_entry(f"entry_{i:03d}", "2026-06-20") for i in range(15)]
    summaries = [_summary(f"summary_{i:03d}", "2026-01-01") for i in range(5)]
    seen = await _walk_pages(_use_case(entries, summaries), size=6, total=20)

    assert len(set(seen)) == 20, len(set(seen))
    assert all(s.startswith("entry_") for s in seen[:15]), seen[:15]
    assert all(s.startswith("summary_") for s in seen[15:]), seen[15:]


async def test_single_type_view_is_untouched() -> None:
    """retro_type 지정 시에는 병합 경로를 타지 않는다(회귀 방지)."""
    entries = [_entry(f"entry_{i:03d}") for i in range(5)]
    items, total = await _use_case(entries, []).execute(
        GetEntriesPageQuery(
            user_id=_USER, retro_type="daily", page=1, size=3, q=None
        )
    )
    assert total == 5, total
    assert [i.id for i in items] == ["entry_004", "entry_003", "entry_002"], items


_TESTS = [
    test_all_same_date_pages_are_disjoint_and_complete,
    test_mixed_dates_with_ties_stay_stable,
    test_one_source_dominates_top_k,
    test_single_type_view_is_untouched,
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
