from datetime import date, datetime

from pydantic import BaseModel, Field

from app.github.domain.models.retrospective_push import RetrospectivePush
from app.retrospective.application.dtos.summary_queries import SummaryReadiness
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.presentation.responses.responses import GithubPushResponse


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
    github_push: GithubPushResponse | None = Field(
        default=None, serialization_alias="githubPush"
    )
    created_at: datetime
    updated_at: datetime | None

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(
        cls,
        summary: RetroSummary,
        push: RetrospectivePush | None = None,
    ) -> "SummaryResponse":
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
            github_push=GithubPushResponse.from_entity(push) if push else None,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )


class SummaryReadinessResponse(BaseModel):
    """`GET /summaries/readiness` 응답.

    measurement: entry 밀도 기반.
    - monthly: expectedUnits = 그 달 일수, coveredUnits = entry 있는 날 수
    - annual : expectedUnits = 12, coveredUnits = entry 있는 월 수
    recommendation: completenessRatio >= 0.7 이면 "ok", 미만이면 "insufficient".
    """
    summary_type: str = Field(serialization_alias="summaryType")
    period_start: date = Field(serialization_alias="periodStart")
    period_end: date = Field(serialization_alias="periodEnd")
    expected_units: int = Field(serialization_alias="expectedUnits")
    covered_units: int = Field(serialization_alias="coveredUnits")
    entry_count: int = Field(serialization_alias="entryCount")
    completeness_ratio: float = Field(serialization_alias="completenessRatio")
    recommendation: str

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, readiness: SummaryReadiness) -> "SummaryReadinessResponse":
        return cls(
            summary_type=readiness.summary_type.value,
            period_start=readiness.period_start,
            period_end=readiness.period_end,
            expected_units=readiness.expected_units,
            covered_units=readiness.covered_units,
            entry_count=readiness.entry_count,
            completeness_ratio=readiness.completeness_ratio,
            recommendation=readiness.recommendation,
        )
