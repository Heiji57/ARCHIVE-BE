"""AI 모듈이 다른 모듈에서 읽어 오는 값 — 다른 도메인의 엔티티를 직접 들고 다니지 않는다."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TodoSnapshot:
    id: str  # 가상 반복 회차면 "{base}::{date}"
    title: str
    date_key: str
    status: str  # not-start | in-progress | done | cancelled
    start_time: datetime | None = None  # UTC
    end_time: datetime | None = None
    timezone: str | None = None
    due_date_key: str | None = None
    tags: tuple[str, ...] = ()
    recurring: bool = False  # 반복 회차(가상 회차·예외 row) — 휴지통으로 보낼 수 없다

    @property
    def tag(self) -> str | None:
        return self.tags[0] if self.tags else None

    @property
    def is_open(self) -> bool:
        return self.status not in ("done", "cancelled")

    @property
    def is_timed(self) -> bool:
        return self.start_time is not None and self.end_time is not None
