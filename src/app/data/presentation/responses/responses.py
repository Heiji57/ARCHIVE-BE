from datetime import datetime

from pydantic import BaseModel, Field

from app.data.domain.models.trash import TrashItem


class TrashItemResponse(BaseModel):
    kind: str
    id: str
    title: str
    date_key: str = Field(serialization_alias="dateKey")
    deleted_at: datetime = Field(serialization_alias="deletedAt")
    purge_at: datetime = Field(serialization_alias="purgeAt")

    @classmethod
    def from_entity(cls, i: TrashItem) -> "TrashItemResponse":
        return cls(
            kind=i.kind,
            id=i.id,
            title=i.title,
            date_key=i.date_key,
            deleted_at=i.deleted_at,
            purge_at=i.purge_at,
        )


class TrashListResponse(BaseModel):
    items: list[TrashItemResponse]
    total: int
    page: int
    size: int


class ExportCreatedResponse(BaseModel):
    id: str


class ExportResponse(BaseModel):
    id: str
    status: str
    scopes: list[str]
    format: str
    created_at: datetime = Field(serialization_alias="createdAt")
    download_url: str | None = Field(default=None, serialization_alias="downloadUrl")
    # 파일을 지우는 시각(완료 + 7일). 내려받기 URL 자체는 24시간짜리라 다시 조회하면 새로 준다.
    expires_at: datetime | None = Field(default=None, serialization_alias="expiresAt")
