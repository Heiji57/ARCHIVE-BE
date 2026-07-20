from datetime import datetime

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
    last_schedule_check_at: datetime | None = Field(serialization_alias="lastScheduleCheckAt")
    calendar_auto_push_todo: bool = Field(serialization_alias="calendarAutoPushTodo")
    calendar_auto_delete_todo: bool = Field(serialization_alias="calendarAutoDeleteTodo")
    github: GitHubSettingsBlock
    active_summary_template_ids: ActiveSummaryTemplateIdsBlock = Field(
        serialization_alias="activeSummaryTemplateIds"
    )

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, s: UserSettings) -> "SettingsResponse":
        return cls(
            locale=s.locale,
            auto_summary_weekly=s.auto_summary_weekly,
            auto_summary_monthly=s.auto_summary_monthly,
            auto_summary_yearly=s.auto_summary_yearly,
            notification_retention_days=s.notification_retention_days,
            last_schedule_check_at=s.last_schedule_check_at,
            calendar_auto_push_todo=s.calendar_auto_push_todo,
            calendar_auto_delete_todo=s.calendar_auto_delete_todo,
            github=GitHubSettingsBlock(
                push_target_repository_id=s.github_push_target_repository_id,
            ),
            active_summary_template_ids=ActiveSummaryTemplateIdsBlock.from_dict(
                s.active_summary_template_ids
            ),
        )
