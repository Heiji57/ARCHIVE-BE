"""JournalEntry / RetroSummary → (period_type, period_key) 매핑.

GitHub push 의 단위(period) 와 entity 단위를 잇는 어댑터.
- period_type 표기는 push API 의 'daily' | 'weekly' | 'monthly' | 'annual' 을 기준으로 한다.
- JournalEntry.retro_type 의 'yearly' 는 push 측 'annual' 로 정규화한다.
"""
from datetime import date, datetime

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import RetroType, SummaryType
from app.shared.domain.utils.period import week_of_month


# RetroType (journal) → push period_type
_JOURNAL_TO_PERIOD_TYPE: dict[RetroType, str] = {
    RetroType.DAILY: "daily",
    RetroType.WEEKLY: "weekly",
    RetroType.MONTHLY: "monthly",
    RetroType.YEARLY: "annual",
}

# SummaryType → push period_type
_SUMMARY_TO_PERIOD_TYPE: dict[SummaryType, str] = {
    SummaryType.WEEKLY: "weekly",
    SummaryType.MONTHLY: "monthly",
    SummaryType.ANNUAL: "annual",
}


def _weekly_key(d: date) -> str:
    year, month, n = week_of_month(d)
    return f"{year:04d}-{month:02d}-W{n}"


def entry_to_period(entry: JournalEntry) -> tuple[str, str]:
    """JournalEntry → (period_type, period_key).

    Raises ValueError 가 발생하지 않도록 retro_type / date_key 는 사전 검증되어 있어야 한다.
    """
    d = datetime.strptime(entry.date_key, "%Y-%m-%d").date()
    rt = entry.retro_type
    period_type = _JOURNAL_TO_PERIOD_TYPE[rt]

    if rt == RetroType.DAILY:
        return period_type, entry.date_key
    if rt == RetroType.WEEKLY:
        return period_type, _weekly_key(d)
    if rt == RetroType.MONTHLY:
        return period_type, f"{d.year:04d}-{d.month:02d}"
    if rt == RetroType.YEARLY:
        return period_type, f"{d.year:04d}"
    raise ValueError(f"Unknown retro_type: {rt}")


def summary_to_period(summary: RetroSummary) -> tuple[str, str]:
    """RetroSummary → (period_type, period_key). period_start 기반."""
    st = summary.summary_type
    period_type = _SUMMARY_TO_PERIOD_TYPE[st]
    d = summary.period_start

    if st == SummaryType.WEEKLY:
        return period_type, _weekly_key(d)
    if st == SummaryType.MONTHLY:
        return period_type, f"{d.year:04d}-{d.month:02d}"
    if st == SummaryType.ANNUAL:
        return period_type, f"{d.year:04d}"
    raise ValueError(f"Unknown summary_type: {st}")
