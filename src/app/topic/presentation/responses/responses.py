from datetime import datetime

from pydantic import BaseModel

from app.topic.domain.models.value_objects import DigestStatus


class TopicResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class TopicDigestResponse(BaseModel):
    id: str
    topic_id: str
    status: DigestStatus
    content: str | None
    watermark_date_key: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
