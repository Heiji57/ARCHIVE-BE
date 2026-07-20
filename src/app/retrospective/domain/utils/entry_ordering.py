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
