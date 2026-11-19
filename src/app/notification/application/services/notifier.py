"""알림 생성의 단일 경로 — 종류별 수신 설정과 방해 금지를 여기서 적용한다.

- `notification_prefs` 에서 꺼진 종류는 **만들지 않는다**(system 은 끌 수 없다).
- `quiet_hours` 안에서 만든 알림은 저장하되 `deliver_after`(방해 금지가 끝나는 UTC 시각)를
  채운다. 목록·SSE 는 그 시각이 지나야 보이고, `worker.flush_quiet_notifications` 가 밀어 준다.
- 저장만 한다. 실시간 전송(Redis pub/sub)은 호출자가 `should_push_now` 를 보고 한다 —
  요청·워커마다 Redis 연결 수명이 달라서다.
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.notification.domain.models.notification import Notification
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.notification.domain.repositories.repository import INotificationRepository
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.user.domain.repositories.repository import IUserRepository

STREAM_CHANNEL = "notifications:{user_id}"


def should_push_now(notification: Notification) -> bool:
    return notification.deliver_after is None


def stream_payload(
    notification: Notification, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`GET /notifications/stream` 이벤트 본문 — 목록 응답(`NotificationResponse`)과 같은 모양."""
    payload: dict[str, Any] = {
        "id": notification.id,
        "type": notification.type.value,
        "category": notification.category.value,
        "title": notification.title,
        "message": notification.message,
        "is_read": notification.is_read,
        "link": notification.link,
        "created_at": notification.created_at.isoformat(),
    }
    link = notification.link or {}
    if link.get("kind") == "summary" and link.get("id"):
        # FE 가 스트림만으로 해당 요약을 다시 읽게 — 보류 후 flush 로 나갈 때도 같은 식별 정보.
        payload.update({"resource": "summary", "summaryId": link["id"]})
    if extra:
        payload.update(extra)
    return payload


class Notifier:
    def __init__(
        self,
        repo: INotificationRepository,
        settings_repo: IUserSettingsRepository,
        user_repo: IUserRepository,
    ) -> None:
        self._repo = repo
        self._settings_repo = settings_repo
        self._user_repo = user_repo

    async def notify(
        self,
        user_id: str,
        *,
        type: NotificationType,
        category: NotificationCategory,
        title: str,
        message: str,
        link: dict[str, Any] | None = None,
        now: datetime | None = None,
        settings: UserSettings | None = None,
    ) -> Notification | None:
        """알림을 저장해 돌려준다. 꺼진 종류면 None.

        `settings` 를 이미 읽었으면 넘겨 재조회를 피한다.
        """
        settings = settings or await self._settings_repo.find_by_user_id(user_id)
        settings = settings or UserSettings.default(user_id)
        if not settings.notification_prefs.allows(category.value):
            return None

        now = now or datetime.now(UTC)
        deliver_after = None
        if settings.quiet_hours.enabled:
            user = await self._user_repo.find_by_id(user_id)
            try:
                tz = ZoneInfo(user.timezone if user else "UTC")
            except (ZoneInfoNotFoundError, ValueError):
                tz = ZoneInfo("UTC")
            local = now.astimezone(tz)
            if settings.quiet_hours.contains(local):
                deliver_after = settings.quiet_hours.ends_after(local).astimezone(UTC)

        notification = Notification.create(
            user_id=user_id,
            type=type,
            category=category,
            title=title,
            message=message,
            link=link,
            deliver_after=deliver_after,
        )
        return await self._repo.save(notification)
