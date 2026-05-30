from datetime import datetime

from pydantic import BaseModel, Field

from app.settings.domain.models.user_settings import UserSettings


class SettingsResponse(BaseModel):
    locale: str
    auto_summary_weekly: bool = Field(serialization_alias="autoSummaryWeekly")
    auto_summary_monthly: bool = Field(serialization_alias="autoSummaryMonthly")
    auto_summary_yearly: bool = Field(serialization_alias="autoSummaryYearly")
    notification_retention_days: int = Field(serialization_alias="notificationRetentionDays")
    last_schedule_check_at: datetime | None = Field(serialization_alias="lastScheduleCheckAt")

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
        )
