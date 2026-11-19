from dataclasses import dataclass

# 부분 수정 sentinel 은 공용 하나 — 모듈마다 클래스가 다르면 isinstance 판정이 어긋난다.
from app.shared.domain.utils.unset import UNSET as UNSET
from app.shared.domain.utils.unset import _Unset as _Unset


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
