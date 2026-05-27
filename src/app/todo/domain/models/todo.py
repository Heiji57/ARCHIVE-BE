from dataclasses import dataclass
from datetime import datetime, timezone

from app.shared.domain.models.base import BaseEntity
from app.todo.domain.exceptions.exceptions import (
    TodoAlreadyCompletedException,
    TodoAlreadyInProgressException,
)
from app.todo.domain.models.value_objects import TaskStatus


@dataclass(kw_only=True)
class Todo(BaseEntity):
    user_id: str
    title: str
    status: TaskStatus
    date_key: str  # YYYY-MM-DD
    description: str = ""
    completed_at: datetime | None = None

    def complete(self) -> None:
        if self.status == TaskStatus.DONE:
            raise TodoAlreadyCompletedException()
        self.status = TaskStatus.DONE
        self.completed_at = datetime.now(timezone.utc)

    def start(self) -> None:
        if self.status == TaskStatus.DONE:
            raise TodoAlreadyCompletedException()
        if self.status == TaskStatus.IN_PROGRESS:
            raise TodoAlreadyInProgressException()
        self.status = TaskStatus.IN_PROGRESS

    def move_to(self, date_key: str) -> None:
        self.date_key = date_key
