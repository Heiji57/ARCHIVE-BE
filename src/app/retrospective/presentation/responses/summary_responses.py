from datetime import date, datetime

from pydantic import BaseModel

from app.retrospective.domain.models.retro_summary import RetroSummary


class SummaryContentResponse(BaseModel):
    achievements: list[str]
    challenges: list[str]
    learnings: list[str]
    next_focus: list[str]


class SummaryResponse(BaseModel):
    id: str
    user_id: str
    summary_type: str
    period_start: date
    period_end: date
    status: str
    content: SummaryContentResponse | None
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, summary: RetroSummary) -> "SummaryResponse":
        return cls(
            id=summary.id,
            user_id=summary.user_id,
            summary_type=summary.summary_type.value,
            period_start=summary.period_start,
            period_end=summary.period_end,
            status=summary.status.value,
            content=SummaryContentResponse(
                achievements=list(summary.content.achievements),
                challenges=list(summary.content.challenges),
                learnings=list(summary.content.learnings),
                next_focus=list(summary.content.next_focus),
            ) if summary.content else None,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )
