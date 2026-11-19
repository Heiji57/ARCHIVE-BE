"""기간 계산 유틸.

주차 산정 규칙(majority-day 방식):
- 주는 사용자 주 시작 요일(`week_start`: "mon" 기본, "sun")부터 7일
- 그 7일 중 더 많은 날이 속한 달이 주의 소유 월
- 같은 달에 속한 주들은 순서대로 1, 2, 3, ... 번호 부여
"""
import calendar
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

WeekStart = Literal["mon", "sun"]


def week_start_of(d: date, week_start: WeekStart = "mon") -> date:
    """date 가 속한 주의 시작일(월요일 또는 일요일)."""
    offset = d.weekday() if week_start == "mon" else (d.weekday() + 1) % 7
    return d - timedelta(days=offset)


def week_start_of_date(start: date) -> WeekStart:
    """주의 시작일로 저장된 날짜에서 그 주의 시작 요일을 되읽는다(일요일이면 sun, 그 외 mon)."""
    return "sun" if start.weekday() == 6 else "mon"


def monday_of_week(d: date) -> date:
    """date가 속한 주의 월요일."""
    return week_start_of(d, "mon")


def owning_month_of_week(start: date) -> tuple[int, int]:
    """주 시작일이 주어졌을 때 그 주의 소유 (year, month). majority-day 방식."""
    week_days = [start + timedelta(days=i) for i in range(7)]
    counts = Counter((d.year, d.month) for d in week_days)
    (year, month), _ = counts.most_common(1)[0]
    return year, month


def weeks_owned_by_month(
    year: int, month: int, week_start: WeekStart = "mon"
) -> list[tuple[date, date]]:
    """해당 월에 귀속되는 주들의 (시작, 끝) 페어 — majority-day 방식.

    예: 2025년 5월
    - 4/28(월)~5/4(일): 3 Apr + 4 May → May W1
    - 5/5(월)~5/11(일): May W2
    - ...
    - 5/26(월)~6/1(일): 6 May + 1 Jun → May W5
    """
    # 후보 월요일 범위: 전월 25일 ~ 차월 7일 사이의 모든 월요일
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    scan_start = first_day - timedelta(days=10)
    scan_end = last_day + timedelta(days=10)

    weeks = []
    cursor = week_start_of(scan_start, week_start)  # cursor 를 주 시작 요일로
    while cursor <= scan_end:
        owning = owning_month_of_week(cursor)
        if owning == (year, month):
            weeks.append((cursor, cursor + timedelta(days=6)))
        cursor += timedelta(days=7)
    return weeks


def get_weeks_in_month(year: int, month: int) -> list[tuple[date, date]]:
    """Deprecated: 기존 코드 호환용. weeks_owned_by_month로 대체된다."""
    return weeks_owned_by_month(year, month)


def get_months_in_year(year: int) -> list[tuple[date, date]]:
    """Return all 12 (first_day, last_day) month periods in the given year."""
    months = []
    for month in range(1, 13):
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        months.append((first_day, last_day))
    return months


def week_of_month(d: date, week_start: WeekStart = "mon") -> tuple[int, int, int]:
    """date가 속한 주의 (소유 year, 소유 month, 주차 번호).

    예: 2025-05-31 → (2025, 5, 5)
        2025-06-01 → (2025, 5, 5)  (다수 5월)
        2025-06-02 → (2025, 6, 1)
    """
    start = week_start_of(d, week_start)
    year, month = owning_month_of_week(start)
    weeks = weeks_owned_by_month(year, month, week_start)
    for idx, (w_start, _) in enumerate(weeks, start=1):
        if w_start == start:
            return year, month, idx
    raise RuntimeError(f"Could not determine week-of-month for {d}")


def today_in_tz(tz: str) -> date:
    """주어진 IANA tz 기준 오늘 날짜."""
    return datetime.now(ZoneInfo(tz)).date()


def now_in_tz(tz: str) -> datetime:
    """주어진 IANA tz 기준 현재 시각."""
    return datetime.now(ZoneInfo(tz))
