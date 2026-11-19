from abc import ABC, abstractmethod
from datetime import date

from app.settings.domain.models.user_settings import UserSettings


class IUserSettingsRepository(ABC):
    @abstractmethod
    async def find_by_user_id(self, user_id: str) -> UserSettings | None: ...

    @abstractmethod
    async def save(self, settings: UserSettings) -> UserSettings: ...

    @abstractmethod
    async def mark_sent(self, user_id: str, **sent_dates: date) -> None:
        """예약 알림·주간 이메일 발송일만 갱신 — 행 전체를 쓰지 않는다.

        키는 `last_due_reminder_date` / `last_day_end_reminder_date` / `last_weekly_email_date`.
        워커가 읽은 뒤 사용자가 PATCH 로 바꾼 다른 설정을 덮어쓰지 않으려는 것.
        """
        ...
