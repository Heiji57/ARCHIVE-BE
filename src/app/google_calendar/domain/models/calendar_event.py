from dataclasses import dataclass
from datetime import datetime

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class CalendarEvent(BaseEntity):
    """Google Calendar 이벤트 스냅샷 (DB 영속화).

    시간 표현은 todo 와 동일 정책:
    - 시간 지정 이벤트: `start_at`/`end_at` 은 UTC TIMESTAMPTZ, `timezone` 은 IANA tz 스냅샷.
      FE 는 `timezone` 으로 로컬 복원.
    - 종일 이벤트: `all_day=True`, `start_at`/`end_at`/`timezone` 은 None, `date_key` 만.

    `date_key` (YYYY-MM-DD) 는 이벤트가 속한 날짜 — todo 와 동일하게 날짜 범위 조회에 사용.
    """
    user_id: str
    connection_id: str
    google_event_id: str
    calendar_id: str
    title: str
    description: str | None = None
    location: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool = False
    date_key: str
    timezone: str | None = None
    status: str = "confirmed"
    html_link: str | None = None
