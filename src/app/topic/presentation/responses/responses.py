from datetime import datetime

from pydantic import BaseModel

from app.todo.presentation.responses.responses import TagCountResponse
from app.topic.domain.models.value_objects import DigestStatus


class TopicResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime | None
    # 목록(GET /topics)에서만 채워진다. 단건 생성/수정 응답에서는 집계를 계산하지 않는다.
    entry_count: int | None = None
    todo_count: int | None = None
    digest_watermark_date_key: str | None = None

    model_config = {"from_attributes": True}


class EntryCountsResponse(BaseModel):
    daily: int
    weekly: int
    monthly: int
    yearly: int
    total: int


class TodoCountsResponse(BaseModel):
    total: int
    completed: int


class TopicStatsResponse(BaseModel):
    topic_id: str
    entry_counts: EntryCountsResponse
    todo_counts: TodoCountsResponse
    tag_counts: list[TagCountResponse]
    tag_count_total: int
    period_start_date_key: str | None
    period_end_date_key: str | None
    unreflected_entry_count: int


class TopicSourceResponse(BaseModel):
    kind: str  # "entry" | "todo"
    id: str
    title: str
    date_key: str
    retro_type: str | None


class TopicSourcePageResponse(BaseModel):
    items: list[TopicSourceResponse]
    total: int
    page: int
    size: int
    digest_watermark_date_key: str | None


class TopicDigestResponse(BaseModel):
    id: str
    topic_id: str
    status: DigestStatus
    content: str | None
    watermark_date_key: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
