"""할 일 모듈의 변경 알림(`TodoChangeObserver`) → AI 행동 학습 기록.

할 일 모듈은 누가 듣는지 모른다. 이 어댑터가 할 일 엔티티를 AI 스냅숏으로 바꾸고 사용자 tz 로
시각을 맞춰 `LearningService` 에 넘긴다. 학습을 껐으면 아무것도 남기지 않는다.
"""

from zoneinfo import ZoneInfo

from app.ai.application.services.learning import LearningService, event_context
from app.ai.infrastructure.adapters.todo_adapter import to_snapshot
from app.todo.domain.models.todo import Todo
from app.user.domain.repositories.repository import IUserRepository


class LearningTodoObserver:
    def __init__(self, learning: LearningService, user_repo: IUserRepository) -> None:
        self._learning = learning
        self._user_repo = user_repo

    async def changed(self, user_id: str, before: Todo, after: Todo) -> None:
        if not await self._learning.enabled(user_id):
            return
        user = await self._user_repo.find_by_id(user_id)
        tz = ZoneInfo(user.timezone if user else "UTC")
        await self._learning.todo_changed(
            user_id, to_snapshot(before), to_snapshot(after), event_context(tz)
        )
