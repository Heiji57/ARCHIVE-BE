from dataclasses import dataclass
from typing import Final


class _Unset:
    """Sentinel for 'field not provided' in partial-update commands.

    omitted (UNSET)  → do not touch the existing value
    explicit None    → clear the existing value (e.g. move folder to root)
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
class CreateFolderCommand:
    user_id: str
    name: str
    parent_folder_id: str | None = None


@dataclass(frozen=True)
class UpdateFolderCommand:
    folder_id: str
    user_id: str
    name: str | None = None
    # sentinel — UNSET(미전송, 이동 없음) vs None(명시적 최상위 이동) 구분
    parent_folder_id: str | None | _Unset = UNSET


@dataclass(frozen=True)
class DeleteFolderCommand:
    folder_id: str
    user_id: str


@dataclass(frozen=True)
class MoveEntryToFolderCommand:
    entry_id: str
    user_id: str
    retro_type: str
    folder_id: str | None
