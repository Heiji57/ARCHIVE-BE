"""사용자 설정 중 서버가 읽는 복합 값 (JSONB 컬럼).

요일은 FE/JS 와 같은 0(일)~6(토). 파이썬 `date.weekday()`(0=월) 와 다르므로
`js_weekday()` 로 바꿔 쓴다. 시각은 "HH:mm" 문자열(사용자 tz 의 벽시계).
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from app.shared.domain.utils.period import WeekStart

__all__ = ["WeekStart"]  # settings 쪽에서 함께 import 하도록 재노출

EmailDigest = Literal["off", "weekly"]

# 알림 종류 중 사용자가 끌 수 있는 것. system 은 항상 받는다.
TOGGLEABLE_CATEGORIES = ("due", "summary", "schedule", "sync", "ai")


def js_weekday(d: date) -> int:
    """0(일)~6(토)."""
    return (d.weekday() + 1) % 7


def parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


@dataclass(frozen=True)
class DayHours:
    start: str  # "HH:mm"
    end: str


_DEFAULT_HOURS = DayHours("09:00", "18:00")


@dataclass(frozen=True)
class WorkSchedule:
    """일하는 요일과 요일별 시간. `per_day` 에 없는 일하는 요일은 첫 일하는 요일의 시간을 쓴다."""

    days: tuple[int, ...] = (1, 2, 3, 4, 5)
    per_day: dict[int, DayHours] = field(default_factory=lambda: {1: _DEFAULT_HOURS})

    def hours_on(self, d: date) -> DayHours | None:
        """그날 일하는 시간. 일하는 날이 아니면 None."""
        wd = js_weekday(d)
        if wd not in self.days:
            return None
        if wd in self.per_day:
            return self.per_day[wd]
        for day in self.days:
            if day in self.per_day:
                return self.per_day[day]
        return _DEFAULT_HOURS

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": list(self.days),
            "perDay": {str(k): {"from": v.start, "to": v.end} for k, v in self.per_day.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "WorkSchedule":
        if not d:
            return cls()
        return cls(
            days=tuple(sorted(int(x) for x in d.get("days", []))),
            per_day={
                int(k): DayHours(v["from"], v["to"]) for k, v in (d.get("perDay") or {}).items()
            },
        )


@dataclass(frozen=True)
class DayEndReminder:
    enabled: bool = False
    at: str = "21:30"

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "at": self.at}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "DayEndReminder":
        return cls(**{**cls().to_dict(), **(d or {})})


@dataclass(frozen=True)
class QuietHours:
    """방해 금지 시간. 자정을 넘을 수 있다(23:00~08:00)."""

    enabled: bool = False
    start: str = "23:00"
    end: str = "08:00"

    def contains(self, local: datetime) -> bool:
        if not self.enabled:
            return False
        t, s, e = local.time(), parse_hhmm(self.start), parse_hhmm(self.end)
        if s == e:
            return False
        return s <= t < e if s < e else (t >= s or t < e)

    def ends_after(self, local: datetime) -> datetime:
        """local 이 방해 금지 안일 때, 끝나는 시각(local 과 같은 tz). 밖이면 local 그대로."""
        if not self.contains(local):
            return local
        e = parse_hhmm(self.end)
        end = datetime.combine(local.date(), e, local.tzinfo)
        return end if end > local else end + timedelta(days=1)

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "from": self.start, "to": self.end}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "QuietHours":
        d = d or {}
        base = cls()
        return cls(
            enabled=bool(d.get("enabled", base.enabled)),
            start=d.get("from", base.start),
            end=d.get("to", base.end),
        )


@dataclass(frozen=True)
class NotificationPrefs:
    due: bool = True
    summary: bool = True
    schedule: bool = True
    sync: bool = True
    ai: bool = True

    def allows(self, category: str) -> bool:
        """꺼진 종류면 False. system(및 모르는 값)은 항상 True."""
        if category not in TOGGLEABLE_CATEGORIES:
            return True
        return bool(getattr(self, category))

    def merged(self, patch: dict[str, bool]) -> "NotificationPrefs":
        return replace(self, **{k: v for k, v in patch.items() if k in TOGGLEABLE_CATEGORIES})

    def to_dict(self) -> dict[str, bool]:
        return {k: getattr(self, k) for k in TOGGLEABLE_CATEGORIES}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "NotificationPrefs":
        return cls().merged({k: bool(v) for k, v in (d or {}).items()})
