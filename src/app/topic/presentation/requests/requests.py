from pydantic import BaseModel, Field


class CreateTopicRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class UpdateTopicRequest(BaseModel):
    """둘 다 선택 — 생략(None)하면 그 필드는 변경하지 않는다."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
