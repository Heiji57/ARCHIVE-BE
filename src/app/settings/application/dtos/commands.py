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
