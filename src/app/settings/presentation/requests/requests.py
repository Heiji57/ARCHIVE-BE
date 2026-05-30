from datetime import datetime

from pydantic import BaseModel, Field


class UpdateSettingsRequest(BaseModel):
    locale: str = Field(default="ko", max_length=10)
    auto_summary_weekly: bool = Field(default=False, alias="autoSummaryWeekly")
    auto_summary_monthly: bool = Field(default=False, alias="autoSummaryMonthly")
    auto_summary_yearly: bool = Field(default=False, alias="autoSummaryYearly")
    notification_retention_days: int = Field(default=30, ge=1, le=365, alias="notificationRetentionDays")
    last_schedule_check_at: datetime | None = Field(default=None, alias="lastScheduleCheckAt")

    model_config = {"populate_by_name": True}
