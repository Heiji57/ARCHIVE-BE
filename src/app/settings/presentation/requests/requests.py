from datetime import datetime

from pydantic import BaseModel, Field


class GitHubSettingsInput(BaseModel):
    """github 네임스페이스 — 향후 확장 가능. push_target_repository_id 미지정 시 null 유지(변경 없음)."""
    push_target_repository_id: str | None = Field(
        default=None, alias="pushTargetRepositoryId"
    )

    model_config = {"populate_by_name": True}


class UpdateSettingsRequest(BaseModel):
    locale: str = Field(default="ko", max_length=10)
    auto_summary_weekly: bool = Field(default=False, alias="autoSummaryWeekly")
    auto_summary_monthly: bool = Field(default=False, alias="autoSummaryMonthly")
    auto_summary_yearly: bool = Field(default=False, alias="autoSummaryYearly")
    notification_retention_days: int = Field(default=30, ge=1, le=365, alias="notificationRetentionDays")
    last_schedule_check_at: datetime | None = Field(default=None, alias="lastScheduleCheckAt")
    github: GitHubSettingsInput = Field(default_factory=GitHubSettingsInput)

    model_config = {"populate_by_name": True}
