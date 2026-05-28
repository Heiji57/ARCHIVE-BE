from dataclasses import dataclass


@dataclass(frozen=True)
class CreateTodoCommand:
    user_id: str
    title: str
    date_key: str
    description: str = ""
    status: str = "not-start"


@dataclass(frozen=True)
class UpdateTodoCommand:
    id: str
    user_id: str
    title: str | None = None
    status: str | None = None
    description: str | None = None
    date_key: str | None = None
