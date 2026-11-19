"""행동 학습 기록 지우기 — `DELETE /ai/learning`. 학습 켜짐/꺼짐은 그대로 둔다."""

from app.ai.application.services.learning import LearningService


class ResetLearningUseCase:
    def __init__(self, learning: LearningService) -> None:
        self._learning = learning

    async def execute(self, user_id: str) -> None:
        await self._learning.reset(user_id)
