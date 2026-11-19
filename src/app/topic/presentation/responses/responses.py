from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.todo.presentation.responses.responses import TagCountResponse
from app.topic.domain.models.value_objects import DigestStatus


class TopicRecentItemResponse(BaseModel):
    date_key: str
    text: str
    theme_key: str


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
    digest_status: str | None = None  # none | pending | in_progress | completed | failed
    digest_summary: str | None = None  # 구조화 정리의 한 줄 요약
    period_start_date_key: str | None = None
    period_end_date_key: str | None = None
    unreflected_entry_count: int | None = None
    recent_items: list[TopicRecentItemResponse] | None = None  # ?include=recent 일 때만

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
    status: str | None = None  # todo 만 — 현재 상태


class TopicSourcePageResponse(BaseModel):
    items: list[TopicSourceResponse]
    total: int
    page: int
    size: int
    digest_watermark_date_key: str | None


class DigestSourceResponse(BaseModel):
    kind: str  # "entry" | "todo"
    title: str
    date_key: str
    retro_type: str | None = None
    status: str | None = None


class TopicDigestResponse(BaseModel):
    id: str
    topic_id: str
    status: DigestStatus
    content: str | None
    # 구조화 정리 {version, summary, themes[{key, name, summary, items[{dateKey, text,
    # source{kind,id}}]}]}. 구조화 도입 전 정리는 null — 다시 정리하면 채워진다.
    structured: dict[str, Any] | None = None
    # structured 가 가리키는 근거 id → 현재 정보. 지운 근거는 빠진다. GET /digest 에서만 채움.
    sources: dict[str, DigestSourceResponse] | None = None
    watermark_date_key: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
