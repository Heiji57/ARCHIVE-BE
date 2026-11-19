from dataclasses import dataclass
from typing import Any

from app.settings.domain.models.preferences import (
    DayEndReminder,
    EmailDigest,
    QuietHours,
    WeekStart,
    WorkSchedule,
)
from app.shared.domain.utils.unset import UNSET, _Unset


@dataclass(frozen=True)
class PatchSettingsCommand:
    """설정 부분 수정. UNSET 인 필드는 기존 값을 유지한다.

    섹션별 PATCH 엔드포인트가 각자 자기 섹션 필드만 채워서 보낸다.
    """

    user_id: str
    locale: str | _Unset = UNSET
    auto_summary_weekly: bool | _Unset = UNSET
    auto_summary_monthly: bool | _Unset = UNSET
    auto_summary_yearly: bool | _Unset = UNSET
    notification_retention_days: int | _Unset = UNSET
    calendar_auto_push_todo: bool | _Unset = UNSET
    calendar_auto_delete_todo: bool | _Unset = UNSET
    # None → push 대상 해제
    github_push_target_repository_id: str | None | _Unset = UNSET
    week_start: WeekStart | _Unset = UNSET
    work_schedule: WorkSchedule | _Unset = UNSET
    default_todo_minutes: int | _Unset = UNSET
    day_end_reminder: DayEndReminder | _Unset = UNSET
    quiet_hours: QuietHours | _Unset = UNSET
    email_digest: EmailDigest | _Unset = UNSET
    # 부분 병합 — 보낸 키만 바뀐다. uiPreferences 는 값이 null 인 키를 지운다.
    notification_prefs: dict[str, bool] | _Unset = UNSET
    ui_preferences: dict[str, Any] | _Unset = UNSET
