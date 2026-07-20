from dataclasses import dataclass


@dataclass(frozen=True)
class GetFolderContentsQuery:
    user_id: str
    folder_id: str | None = None  # None — 최상위(root)
    retro_type: str | None = None  # None — 전체 타입 합산 뷰
    page: int = 1
    size: int = 10
