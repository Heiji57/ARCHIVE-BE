from dataclasses import dataclass
from datetime import date, datetime


@dataclass(kw_only=True)
class UserSettings:
    user_id: str
    locale: str = "ko"
    auto_summary_weekly: bool = False
    auto_summary_monthly: bool = False
    auto_summary_yearly: bool = False
    notification_retention_days: int = 30
    last_schedule_check_at: datetime | None = None
    last_summary_date_local: date | None = None
    github_push_target_repository_id: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def default(cls, user_id: str) -> "UserSettings":
        return cls(user_id=user_id)
