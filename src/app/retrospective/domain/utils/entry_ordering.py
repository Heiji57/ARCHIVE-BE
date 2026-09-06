from datetime import date

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary


def content_date(item: JournalEntry | RetroSummary) -> date:
    """merge 정렬 기준 — journal entry 는 date_key(회고 대상 일자), summary 는
    period_start(요약 대상 기간 시작일). created_at(레코드 생성 시각) 대신 이걸
    쓰는 이유: 나중에 백필한 과거 회고가 오늘 날짜로 최상단에 뜨면 안 되므로,
    단일 타입 조회(date_key/period_start 정렬)와 동일한 기준으로 통일한다."""
    if isinstance(item, JournalEntry):
        return date.fromisoformat(item.date_key)
    return item.period_start


def merge_sorted_desc(
    entries: list[JournalEntry], summaries: list[RetroSummary]
) -> list[JournalEntry | RetroSummary]:
    """daily(journal_entries) + weekly/monthly/annual(retro_summaries) 를 합쳐
    content_date 기준 최신순으로 정렬한다 ("전체" 뷰 병합 공통 로직)."""
    return sorted([*entries, *summaries], key=content_date, reverse=True)


def content_order_key(item: JournalEntry | RetroSummary) -> tuple[date, str]:
    """(content_date, id) — 통합 페이지네이션용 결정적 정렬 키.

    id tie-break 가 없으면 같은 날짜의 항목들 사이 순서가 비결정적이라
    페이지 경계에서 항목이 누락되거나 중복된다."""
    return content_date(item), item.id


def merge_sorted_desc_with_id(
    entries: list[JournalEntry], summaries: list[RetroSummary]
) -> list[JournalEntry | RetroSummary]:
    """merge_sorted_desc 의 결정적 버전 — 두 소스를 합친 뒤 전체에 대해
    (날짜 DESC, id DESC) 로 정렬한다. UNION 결과 전체에
    `ORDER BY date_key DESC, id DESC` 를 건 것과 같은 순서다.

    각 소스도 같은 기준(날짜 DESC, id DESC)으로 상위 N개를 가져와야
    "각 소스 상위 N개면 전역 상위 N개를 항상 커버한다"는 성질이 성립한다
    (`GET /folders/contents` 의 통합 페이지네이션에서 사용)."""
    return sorted([*entries, *summaries], key=content_order_key, reverse=True)
