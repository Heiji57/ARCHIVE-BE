from dataclasses import dataclass
from datetime import datetime
from typing import Final


class _Unset:
    """Sentinel for 'field not provided' in partial-update commands.

    omitted (UNSET)  → do not touch the existing value
    explicit None    → clear the existing value
    """

    _instance: "_Unset | None" = None

    def __new__(cls) -> "_Unset":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<UNSET>"

    def __bool__(self) -> bool:
        return False


UNSET: Final[_Unset] = _Unset()


@dataclass(frozen=True)
class CreateTodoCommand:
    user_id: str
    title: str
    date_key: str
    description: str = ""
    status: str = "not-start"
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None


@dataclass(frozen=True)
class UpdateTodoCommand:
    id: str
    user_id: str
    title: str | None = None
    status: str | None = None
    description: str | None = None
    date_key: str | None = None
    # 시간 필드는 sentinel — UNSET(미전송) vs None(명시 clear) 구분
    start_time: datetime | None | _Unset = UNSET
    end_time: datetime | None | _Unset = UNSET
    timezone: str | None | _Unset = UNSET
