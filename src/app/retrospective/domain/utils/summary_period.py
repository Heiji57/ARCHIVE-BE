"""SummaryType 별 기간 계산.

request_summary use case 와 get_summary_readiness use case 가 공유한다.
"""
import calendar
from datetime import date, timedelta

from app.retrospective.domain.models.value_objects import SummaryType


def calculate_summary_period(
    summary_type: SummaryType, period_start: date | None
) -> tuple[date, date]:
    """summary_type 과 period_start 로 (start, end) 계산.

    period_start 가 None 이면 직전 기간으로 fallback:
    - WEEKLY: 직전 완전한 월~일 (오늘 기준 지난 주)
    - MONTHLY: 지난 달 전체
    - ANNUAL: 작년 전체
    """
    if period_start is not None:
        # 입력이 기간 중 어느 날이든 기간 시작으로 정규화한다.
        # 동일 주/월/년은 항상 같은 period_start 로 수렴 → unique constraint
        # (user_id, summary_type, period_start) 가 중복 생성을 정상 차단한다.
        if summary_type == SummaryType.WEEKLY:
            monday = period_start - timedelta(days=period_start.weekday())
            return monday, monday + timedelta(days=6)
        if summary_type == SummaryType.MONTHLY:
            first = period_start.replace(day=1)
            last_day = calendar.monthrange(first.year, first.month)[1]
            return first, first.replace(day=last_day)
        first = period_start.replace(month=1, day=1)
        return first, first.replace(month=12, day=31)

    today = date.today()

    if summary_type == SummaryType.WEEKLY:
        last_sunday = today - timedelta(days=today.weekday() + 1)
        last_monday = last_sunday - timedelta(days=6)
        return last_monday, last_sunday

    if summary_type == SummaryType.MONTHLY:
        first_of_last = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last_day = calendar.monthrange(first_of_last.year, first_of_last.month)[1]
        return first_of_last, first_of_last.replace(day=last_day)

    last_year = today.year - 1
    return date(last_year, 1, 1), date(last_year, 12, 31)
