import re
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.settings.domain.models.preferences import (
    DayEndReminder,
    DayHours,
    QuietHours,
    WorkSchedule,
)

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _check_hhmm(v: str) -> str:
    if not _HHMM.fullmatch(v):
        raise ValueError("time must be HH:mm (00:00~23:59)")
    return v


class DayHoursInput(BaseModel):
    start: str = Field(alias="from")
    end: str = Field(alias="to")

    model_config = {"populate_by_name": True}

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        return _check_hhmm(v)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        # 자정을 넘는 근무는 1차 범위 밖 — 하루 안에서 시작 < 끝.
        if self.start >= self.end:
            raise ValueError("from must be earlier than to")
        return self


class WorkScheduleInput(BaseModel):
    """`days` 는 0(일)~6(토). `perDay` 키도 같은 요일 번호(문자열)."""

    days: list[int]
    per_day: dict[str, DayHoursInput] = Field(default_factory=dict, alias="perDay")

    model_config = {"populate_by_name": True}

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v) or len(set(v)) != len(v):
            raise ValueError("days must be unique weekdays 0(Sun)~6(Sat)")
        return sorted(v)

    @field_validator("per_day")
    @classmethod
    def _per_day(cls, v: dict[str, DayHoursInput]) -> dict[str, DayHoursInput]:
        if any(k not in {str(i) for i in range(7)} for k in v):
            raise ValueError("perDay keys must be weekdays '0'~'6'")
        return v

    def to_domain(self) -> WorkSchedule:
        return WorkSchedule(
            days=tuple(self.days),
            per_day={int(k): DayHours(h.start, h.end) for k, h in self.per_day.items()},
        )


class DayEndReminderInput(BaseModel):
    enabled: bool
    at: str

    @field_validator("at")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        return _check_hhmm(v)

    def to_domain(self) -> DayEndReminder:
        return DayEndReminder(enabled=self.enabled, at=self.at)


class QuietHoursInput(BaseModel):
    """자정을 넘어도 된다(23:00~08:00). from == to 는 비어 있는 구간이라 거절."""

    enabled: bool
    start: str = Field(alias="from")
    end: str = Field(alias="to")

    model_config = {"populate_by_name": True}

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        return _check_hhmm(v)

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.start == self.end:
            raise ValueError("from and to must differ")
        return self

    def to_domain(self) -> QuietHours:
        return QuietHours(enabled=self.enabled, start=self.start, end=self.end)


class NotificationPrefsInput(BaseModel):
    """보낸 종류만 바뀐다. system 은 끌 수 없어 받지 않는다."""

    due: bool | None = None
    summary: bool | None = None
    schedule: bool | None = None
    sync: bool | None = None
    ai: bool | None = None

    def provided(self) -> dict[str, bool]:
        return {k: getattr(self, k) for k in self.model_fields_set if getattr(self, k) is not None}


class _SettingsPatchBody(BaseModel):
    """섹션별 설정 PATCH 공통 베이스.

    - 보내지 않은 필드는 변경하지 않는다(`model_fields_set` 으로 구분).
    - `_NULLABLE` 에 없는 필드에 명시적 null 이 오면 422.
    """

    _NULLABLE: ClassVar[frozenset[str]] = frozenset()

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _reject_null(self) -> Self:
        for name in self.model_fields_set:
            if getattr(self, name) is None and name not in self._NULLABLE:
                raise ValueError(f"{name} must not be null")
        return self

    def provided(self) -> dict[str, Any]:
        """전송된 필드만 {필드명: 값} 으로. 중첩 입력은 도메인 값으로 바꾼다."""
        out: dict[str, Any] = {}
        for name in self.model_fields_set:
            value = getattr(self, name)
            if isinstance(value, NotificationPrefsInput):
                value = value.provided()
            elif hasattr(value, "to_domain"):
                value = value.to_domain()
            out[name] = value
        return out


class GeneralSettingsPatchRequest(_SettingsPatchBody):
    """`PATCH /settings/general`"""

    locale: str | None = Field(default=None, max_length=10)
    week_start: Literal["mon", "sun"] | None = Field(default=None, alias="weekStart")
    # 화면 설정 — 서버는 해석하지 않는다. 보낸 키만 병합, 값이 null 인 키는 지운다. 8KB 상한.
    ui_preferences: dict[str, Any] | None = Field(default=None, alias="uiPreferences")

    @field_validator("locale")
    @classmethod
    def _normalize_locale(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip().lower() or "ko"


class AutoSummarySettingsPatchRequest(_SettingsPatchBody):
    """`PATCH /settings/auto-summary`"""

    auto_summary_weekly: bool | None = Field(default=None, alias="autoSummaryWeekly")
    auto_summary_monthly: bool | None = Field(default=None, alias="autoSummaryMonthly")
    auto_summary_yearly: bool | None = Field(default=None, alias="autoSummaryYearly")


class NotificationSettingsPatchRequest(_SettingsPatchBody):
    """`PATCH /settings/notifications`"""

    notification_retention_days: int | None = Field(
        default=None, ge=1, le=365, alias="notificationRetentionDays"
    )
    notification_prefs: NotificationPrefsInput | None = Field(
        default=None, alias="notificationPrefs"
    )
    quiet_hours: QuietHoursInput | None = Field(default=None, alias="quietHours")
    email_digest: Literal["off", "weekly"] | None = Field(default=None, alias="emailDigest")


class WorkSettingsPatchRequest(_SettingsPatchBody):
    """`PATCH /settings/work` — 일하는 시간, 기본 할 일 길이, 하루 마무리 알림."""

    work_schedule: WorkScheduleInput | None = Field(default=None, alias="workSchedule")
    default_todo_minutes: int | None = Field(
        default=None, ge=15, le=480, alias="defaultTodoMinutes"
    )
    day_end_reminder: DayEndReminderInput | None = Field(default=None, alias="dayEndReminder")


class CalendarSettingsPatchRequest(_SettingsPatchBody):
    """`PATCH /settings/calendar`"""

    calendar_auto_push_todo: bool | None = Field(default=None, alias="calendarAutoPushTodo")
    calendar_auto_delete_todo: bool | None = Field(default=None, alias="calendarAutoDeleteTodo")


class GitHubSettingsPatchRequest(_SettingsPatchBody):
    """`PATCH /settings/github` — `pushTargetRepositoryId: null` 은 push 대상 해제."""

    _NULLABLE: ClassVar[frozenset[str]] = frozenset({"push_target_repository_id"})

    push_target_repository_id: str | None = Field(default=None, alias="pushTargetRepositoryId")


class ActiveSummaryTemplateIdsRequest(BaseModel):
    """`PUT /settings/auto-summary/active` body.

    각 필드:
    - 문자열 → 해당 summary_type 의 활성 템플릿 id (소유/타입 일치 검증)
    - null   → 해당 type 비활성화 → 시스템 기본 템플릿 사용
    - 미전송 → 변경 안 함
    """
    weekly: str | None = Field(default=None)
    monthly: str | None = Field(default=None)
    annual: str | None = Field(default=None)

    model_config = {"populate_by_name": True}


class UnsubscribeRequest(BaseModel):
    """`POST /settings/email-digest/unsubscribe` — 메일 링크의 서명 토큰."""

    token: str = Field(min_length=1)
