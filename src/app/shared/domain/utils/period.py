import calendar
from datetime import date, timedelta


def get_weeks_in_month(year: int, month: int) -> list[tuple[date, date]]:
    """Return Mon-Sun week periods where Monday falls within the given month."""
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    days_until_monday = (7 - first_day.weekday()) % 7
    first_monday = first_day if first_day.weekday() == 0 else first_day + timedelta(days=days_until_monday)

    weeks = []
    current = first_monday
    while current <= last_day:
        weeks.append((current, current + timedelta(days=6)))
        current += timedelta(days=7)
    return weeks


def get_months_in_year(year: int) -> list[tuple[date, date]]:
    """Return all 12 (first_day, last_day) month periods in the given year."""
    months = []
    for month in range(1, 13):
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        months.append((first_day, last_day))
    return months
