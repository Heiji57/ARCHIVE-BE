import re

from pydantic import BaseModel, Field, field_validator

_VALID_RETRO_TYPES = {"daily", "weekly", "monthly", "yearly"}
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SUMMARY_EDIT_MAX_LEN = 50_000


class EntryCreateRequest(BaseModel):
    date_key: str
    # 생략/공백 시 서버가 "{date_key} {회고 종류}" 로 채운다 (사용자 locale 기준).
    title: str | None = None
    content: str = ""
    retro_type: str = "daily"

    @field_validator("retro_type")
    @classmethod
    def retro_type_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_RETRO_TYPES:
            raise ValueError(f"retro_type must be one of {_VALID_RETRO_TYPES}")
        return v

    @field_validator("date_key")
    @classmethod
    def date_key_format(cls, v: str) -> str:
        if not _DATE_RE.fullmatch(v):
            raise ValueError("date_key must be in YYYY-MM-DD format")
        return v


class SummaryEditRequest(BaseModel):
    """요약 마크다운 오버라이드. contentMarkdown=null 이면 편집 해제(AI 원본 복귀)."""

    content_markdown: str | None = Field(alias="contentMarkdown")

    model_config = {"populate_by_name": True}

    @field_validator("content_markdown")
    @classmethod
    def content_markdown_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) > _SUMMARY_EDIT_MAX_LEN:
            raise ValueError(
                f"contentMarkdown must be {_SUMMARY_EDIT_MAX_LEN} characters or fewer"
            )
        return v


class EntryUpsertRequest(BaseModel):
    date_key: str
    title: str
    content: str = ""
    retro_type: str = "daily"

    @field_validator("retro_type")
    @classmethod
    def retro_type_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_RETRO_TYPES:
            raise ValueError(f"retro_type must be one of {_VALID_RETRO_TYPES}")
        return v

    @field_validator("date_key")
    @classmethod
    def date_key_format(cls, v: str) -> str:
        if not _DATE_RE.fullmatch(v):
            raise ValueError("date_key must be in YYYY-MM-DD format")
        return v
