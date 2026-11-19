"""예약한 일의 실행 시각 판정(순수). 시각은 사용자 tz 의 벽시계."""

from datetime import datetime, timedelta

from app.ai.domain.models.ai_settings import AiSchedule

CATCH_UP = timedelta(hours=1)  # 늦은 beat 보정 — 정한 시각부터 1시간 안이면 실행


def _js_weekday(dt: datetime) -> int:
    return (dt.weekday() + 1) % 7


def schedule_due(schedule: AiSchedule, local_now: datetime) -> bool:
    """켜져 있고, 오늘 실행하는 날이고, 시각이 지났고(1시간 안), 오늘 아직 안 돌렸다."""
    if not schedule.enabled or schedule.last_run_date == local_now.date():
        return False
    repeat = schedule.repeat
    if repeat.get("unit") == "week" and _js_weekday(local_now) not in (
        repeat.get("weekdays") or []
    ):
        return False
    hh, mm = (int(x) for x in str(repeat.get("at", "09:00")).split(":"))
    start = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return start <= local_now < start + CATCH_UP
