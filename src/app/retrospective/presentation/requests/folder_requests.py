from pydantic import BaseModel, Field


class FolderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_folder_id: str | None = Field(default=None, alias="parentFolderId")

    model_config = {"populate_by_name": True}


class FolderUpdateRequest(BaseModel):
    """PATCH 부분 수정 — 전송된 필드만 갱신.

    parentFolderId: 문자열 → 그 폴더로 이동 / 명시적 null → 최상위로 이동 /
    미전송 → 이동 없음(model_fields_set 으로 구분).
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_folder_id: str | None = Field(default=None, alias="parentFolderId")

    model_config = {"populate_by_name": True}


class MoveEntryFolderRequest(BaseModel):
    folder_id: str | None = Field(alias="folderId")

    model_config = {"populate_by_name": True}
