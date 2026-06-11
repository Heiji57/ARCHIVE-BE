from datetime import datetime

from pydantic import BaseModel

from app.todo.domain.models.todo import Todo


class TodoResponse(BaseModel):
    id: str
    user_id: str
    title: str
    status: str
    date_key: str
    description: str
    completed: bool
    start_time: str | None
    end_time: str | None
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_entity(cls, todo: Todo) -> "TodoResponse":
        return cls(
            id=todo.id,
            user_id=todo.user_id,
            title=todo.title,
            status=todo.status.value,
            date_key=todo.date_key,
            description=todo.description,
            completed=todo.status.value == "done",
            start_time=todo.start_time,
            end_time=todo.end_time,
            created_at=todo.created_at,
            updated_at=todo.updated_at,
            completed_at=todo.completed_at,
        )
