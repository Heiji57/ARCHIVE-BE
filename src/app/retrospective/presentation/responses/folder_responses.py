from datetime import datetime

from pydantic import BaseModel, Field

from app.retrospective.application.use_cases.get_folder_contents import FolderWithCounts
from app.retrospective.domain.models.folder import Folder
from app.retrospective.presentation.responses.responses import EntryWithGithubResponse


class FolderResponse(BaseModel):
    id: str
    user_id: str = Field(serialization_alias="userId")
    name: str
    parent_folder_id: str | None = Field(default=None, serialization_alias="parentFolderId")
    folder_count: int = Field(default=0, serialization_alias="folderCount")
    entry_count: int = Field(default=0, serialization_alias="entryCount")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, folder: Folder) -> "FolderResponse":
        return cls(
            id=folder.id,
            user_id=folder.user_id,
            name=folder.name,
            parent_folder_id=folder.parent_folder_id,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
        )

    @classmethod
    def from_with_counts(cls, fwc: FolderWithCounts) -> "FolderResponse":
        return cls(
            id=fwc.folder.id,
            user_id=fwc.folder.user_id,
            name=fwc.folder.name,
            parent_folder_id=fwc.folder.parent_folder_id,
            folder_count=fwc.folder_count,
            entry_count=fwc.entry_count,
            created_at=fwc.folder.created_at,
            updated_at=fwc.folder.updated_at,
        )


class FolderContentsResponse(BaseModel):
    """GET /folders/contents 응답 — 하위 폴더와 회고록을 타입별로 분리해서 반환한다
    (search 모듈의 {todos, entries} 분리와 동일한 이유 — 서로 다른 성격의 리소스를
    억지로 하나의 배열에 합치지 않는다).

    두 배열은 폴더와 회고록을 합친 단일 시퀀스에 대한 페이지 조각이다 —
    folders(이 페이지 구간의 폴더 조각) 뒤에 entries(폴더가 쓰고 남은 칸을 채운
    회고록 조각)가 이어지며 `len(folders) + len(entries) <= size` 를 항상 만족한다.
    total 은 폴더 총개수 + 회고록 총건수(페이지 무관)로, 폴더 개수는 retroType 과
    무관하고 회고록 건수에만 retroType 필터가 적용된다."""

    folders: list[FolderResponse]
    entries: list[EntryWithGithubResponse]
    total: int
    page: int
    size: int

    model_config = {"populate_by_name": True}
