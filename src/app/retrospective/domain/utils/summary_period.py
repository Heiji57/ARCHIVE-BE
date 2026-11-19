"""SummaryType 별 기간 계산.

request_summary use case 와 get_summary_readiness use case 가 공유한다.
"""
import calendar
from datetime import date, timedelta

from app.retrospective.domain.models.value_objects import SummaryType
from app.shared.domain.utils.period import WeekStart, week_start_of


def adjust_week_after_start_change(
    start: date, end: date, previous_end: date | None
) -> tuple[date, date] | None:
    """주 시작 요일을 바꾼 직후 주의 경계 보정 — 이미 만든 주간 요약과 겹치거나 비지 않게.

    이미 만든 요약은 다시 계산하지 않는다(결정 2026-11-16). 대신 바꾼 주만 6일 또는 8일로 둔다.
    - 월→일: 직전 요약(월~일)과 하루 겹친다 → 그날을 빼 6일.
    - 일→월: 첫 월요일 트리거의 주(월~일)는 직전 요약(일~토)이 6일을 이미 덮었다 → 이 주는
      건너뛰고(None), 다음 주가 비는 하루(일)를 넣어 8일이 된다.
    직전 요약이 바로 앞 주가 아니면(오래 쉬었음) 보정하지 않는다.
    """
    if previous_end is None or previous_end < start - timedelta(days=2):
        return start, end
    if previous_end >= end:
        return None
    if previous_end >= start:
        trimmed = previous_end + timedelta(days=1)
        # 남는 날이 반도 안 되면 이 주는 이미 덮인 것 — 다음 주가 남는 날을 가져간다.
        return (trimmed, end) if (end - trimmed).days + 1 >= 4 else None
    if previous_end == start - timedelta(days=2):
        return start - timedelta(days=1), end
    return start, end


def calculate_summary_period(
    summary_type: SummaryType,
    period_start: date | None,
    week_start: WeekStart = "mon",
    today: date | None = None,
) -> tuple[date, date]:
    """summary_type 과 period_start 로 (start, end) 계산.

    period_start 가 None 이면 직전 기간으로 fallback:
    - WEEKLY: 직전 완전한 주 (사용자 주 시작 요일 기준, 오늘 기준 지난 주)
    - MONTHLY: 지난 달 전체
    - ANNUAL: 작년 전체
    """
    if period_start is not None:
        # 입력이 기간 중 어느 날이든 기간 시작으로 정규화한다.
        # 동일 주/월/년은 항상 같은 period_start 로 수렴 → unique constraint
        # (user_id, summary_type, period_start) 가 중복 생성을 정상 차단한다.
        if summary_type == SummaryType.WEEKLY:
            start = week_start_of(period_start, week_start)
            return start, start + timedelta(days=6)
        if summary_type == SummaryType.MONTHLY:
            first = period_start.replace(day=1)
            last_day = calendar.monthrange(first.year, first.month)[1]
            return first, first.replace(day=last_day)
        first = period_start.replace(month=1, day=1)
        return first, first.replace(month=12, day=31)

    today = today or date.today()

    if summary_type == SummaryType.WEEKLY:
        this_week = week_start_of(today, week_start)
        return this_week - timedelta(days=7), this_week - timedelta(days=1)

    if summary_type == SummaryType.MONTHLY:
        first_of_last = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last_day = calendar.monthrange(first_of_last.year, first_of_last.month)[1]
        return first_of_last, first_of_last.replace(day=last_day)

    last_year = today.year - 1
    return date(last_year, 1, 1), date(last_year, 12, 31)
