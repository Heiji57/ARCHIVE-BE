from typing import Any

from pydantic import BaseModel, Field

from app.settings.domain.models.user_settings import UserSettings


class GitHubSettingsBlock(BaseModel):
    push_target_repository_id: str | None = Field(
        default=None, serialization_alias="pushTargetRepositoryId"
    )

    model_config = {"populate_by_name": True}


class ActiveSummaryTemplateIdsBlock(BaseModel):
    """summary_type 별 활성 템플릿 ID. null 이면 시스템 기본 사용."""
    weekly: str | None = Field(default=None)
    monthly: str | None = Field(default=None)
    annual: str | None = Field(default=None)

    model_config = {"populate_by_name": True}

    @classmethod
    def from_dict(cls, d: dict[str, str | None]) -> "ActiveSummaryTemplateIdsBlock":
        return cls(
            weekly=d.get("weekly"),
            monthly=d.get("monthly"),
            annual=d.get("annual"),
        )


class SettingsResponse(BaseModel):
    locale: str
    auto_summary_weekly: bool = Field(serialization_alias="autoSummaryWeekly")
    auto_summary_monthly: bool = Field(serialization_alias="autoSummaryMonthly")
    auto_summary_yearly: bool = Field(serialization_alias="autoSummaryYearly")
    notification_retention_days: int = Field(serialization_alias="notificationRetentionDays")
    calendar_auto_push_todo: bool = Field(serialization_alias="calendarAutoPushTodo")
    calendar_auto_delete_todo: bool = Field(serialization_alias="calendarAutoDeleteTodo")
    github: GitHubSettingsBlock
    active_summary_template_ids: ActiveSummaryTemplateIdsBlock = Field(
        serialization_alias="activeSummaryTemplateIds"
    )
    week_start: str = Field(serialization_alias="weekStart")
    # {days: [0~6], perDay: {"1": {from, to}}} — 요일은 0(일)~6(토)
    work_schedule: dict[str, Any] = Field(serialization_alias="workSchedule")
    default_todo_minutes: int = Field(serialization_alias="defaultTodoMinutes")
    day_end_reminder: dict[str, Any] = Field(serialization_alias="dayEndReminder")
    notification_prefs: dict[str, bool] = Field(serialization_alias="notificationPrefs")
    quiet_hours: dict[str, Any] = Field(serialization_alias="quietHours")
    email_digest: str = Field(serialization_alias="emailDigest")
    ui_preferences: dict[str, Any] = Field(serialization_alias="uiPreferences")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, s: UserSettings) -> "SettingsResponse":
        return cls(
            locale=s.locale,
            auto_summary_weekly=s.auto_summary_weekly,
            auto_summary_monthly=s.auto_summary_monthly,
            auto_summary_yearly=s.auto_summary_yearly,
            notification_retention_days=s.notification_retention_days,
            calendar_auto_push_todo=s.calendar_auto_push_todo,
            calendar_auto_delete_todo=s.calendar_auto_delete_todo,
            github=GitHubSettingsBlock(
                push_target_repository_id=s.github_push_target_repository_id,
            ),
            active_summary_template_ids=ActiveSummaryTemplateIdsBlock.from_dict(
                s.active_summary_template_ids
            ),
            week_start=s.week_start,
            work_schedule=s.work_schedule.to_dict(),
            default_todo_minutes=s.default_todo_minutes,
            day_end_reminder=s.day_end_reminder.to_dict(),
            notification_prefs=s.notification_prefs.to_dict(),
            quiet_hours=s.quiet_hours.to_dict(),
            email_digest=s.email_digest,
            ui_preferences=dict(s.ui_preferences),
        )
