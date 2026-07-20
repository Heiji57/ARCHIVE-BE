"""기간 계산 유틸.

주차 산정 규칙(majority-day 방식):
- 주는 월요일 시작 ~ 일요일 종료 (ISO 8601)
- 그 7일 중 더 많은 날이 속한 달이 주의 소유 월
- 같은 달에 속한 주들은 순서대로 1, 2, 3, ... 번호 부여
"""
import calendar
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def monday_of_week(d: date) -> date:
    """date가 속한 주의 월요일."""
    return d - timedelta(days=d.weekday())


def owning_month_of_week(monday: date) -> tuple[int, int]:
    """월요일이 주어졌을 때 그 주의 소유 (year, month). majority-day 방식."""
    week_days = [monday + timedelta(days=i) for i in range(7)]
    counts = Counter((d.year, d.month) for d in week_days)
    (year, month), _ = counts.most_common(1)[0]
    return year, month


def weeks_owned_by_month(year: int, month: int) -> list[tuple[date, date]]:
    """해당 월에 귀속되는 주들의 (월, 일) 페어 — majority-day 방식.

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
    cursor = scan_start - timedelta(days=scan_start.weekday())  # cursor를 월요일로
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


def week_of_month(d: date) -> tuple[int, int, int]:
    """date가 속한 주의 (소유 year, 소유 month, 주차 번호).

    예: 2025-05-31 → (2025, 5, 5)
        2025-06-01 → (2025, 5, 5)  (다수 5월)
        2025-06-02 → (2025, 6, 1)
    """
    monday = monday_of_week(d)
    year, month = owning_month_of_week(monday)
    weeks = weeks_owned_by_month(year, month)
    for idx, (w_start, _) in enumerate(weeks, start=1):
        if w_start == monday:
            return year, month, idx
    raise RuntimeError(f"Could not determine week-of-month for {d}")


def today_in_tz(tz: str) -> date:
    """주어진 IANA tz 기준 오늘 날짜."""
    return datetime.now(ZoneInfo(tz)).date()


def now_in_tz(tz: str) -> datetime:
    """주어진 IANA tz 기준 현재 시각."""
    return datetime.now(ZoneInfo(tz))
