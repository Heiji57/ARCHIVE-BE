"""TrashedTodosNotice 구현 — 알림 모듈의 Notifier 로 `category: sync` 알림 하나를 만든다.

저장만 한다(SSE 실시간 전송 없음) — 동기화는 요청·워커 어느 쪽에서도 돌아 Redis 연결 수명이
제각각이다. FE 는 알림 목록을 다시 읽을 때 본다.
"""

from app.notification.application.services.notifier import Notifier
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.settings.domain.repositories.repository import IUserSettingsRepository

_TEXT = {
    "ko": ("캘린더 동기화", "Google에서 지운 일정 {n}개를 휴지통으로 옮겼어요"),
    "en": ("Calendar sync", "Moved {n} todos deleted in Google Calendar to the trash"),
}


class NotifierTrashNotice:
    def __init__(self, notifier: Notifier, settings_repo: IUserSettingsRepository) -> None:
        self._notifier = notifier
        self._settings_repo = settings_repo

    async def todos_trashed(self, user_id: str, count: int) -> None:
        settings = await self._settings_repo.find_by_user_id(user_id)
        locale = settings.locale if settings else "ko"
        title, message = _TEXT["ko" if (locale or "ko").startswith("ko") else "en"]
        await self._notifier.notify(
            user_id,
            type=NotificationType.INFO,
            category=NotificationCategory.SYNC,
            title=title,
            message=message.format(n=count),
            link={"kind": "trash"},
            settings=settings,
        )
