"""google_calendar 응용 계층이 다른 모듈 기능을 쓰는 좁은 포트."""

from typing import Protocol


class TrashedTodosNotice(Protocol):
    async def todos_trashed(self, user_id: str, count: int) -> None:
        """Google 에서 지운 일정 n개의 할 일을 휴지통으로 옮겼다 — 동기화 한 번에 알림 하나."""
        ...
