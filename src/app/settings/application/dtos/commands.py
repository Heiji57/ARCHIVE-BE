from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UpdateSettingsCommand:
    user_id: str
    locale: str
    auto_summary_weekly: bool
    auto_summary_monthly: bool
    auto_summary_yearly: bool
    notification_retention_days: int
    last_schedule_check_at: datetime | None
    calendar_auto_push_todo: bool = False
    calendar_auto_delete_todo: bool = False
    github_push_target_repository_id: str | None = None
