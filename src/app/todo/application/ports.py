"""할 일 모듈이 바깥에 알리는 좁은 포트.

할 일 모듈은 누가 듣는지 모른다 — 구현은 듣는 모듈(예: AI 행동 학습)이 맡고 DI 로 묶는다.
"""

from typing import Protocol

from app.todo.domain.models.todo import Todo


class TodoChangeObserver(Protocol):
    async def changed(self, user_id: str, before: Todo, after: Todo) -> None:
        """사용자가 할 일 하나(한 회차)를 고친 뒤. 요청 트랜잭션 안에서 불린다."""
        ...
