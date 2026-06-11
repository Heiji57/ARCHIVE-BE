from datetime import datetime

from pydantic import BaseModel, Field

from app.retrospective.domain.models.summary_template import UserSummaryTemplate


class SummaryTemplateResponse(BaseModel):
    id: str
    user_id: str = Field(serialization_alias="userId")
    summary_type: str = Field(serialization_alias="summaryType")
    name: str
    content: str
    is_active: bool = Field(serialization_alias="isActive")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(
        cls, t: UserSummaryTemplate, *, is_active: bool
    ) -> "SummaryTemplateResponse":
        return cls(
            id=t.id,
            user_id=t.user_id,
            summary_type=t.summary_type.value,
            name=t.name,
            content=t.content,
            is_active=is_active,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
