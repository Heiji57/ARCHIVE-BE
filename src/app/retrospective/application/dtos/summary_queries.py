from dataclasses import dataclass
from datetime import date

from app.retrospective.domain.models.value_objects import SummaryType


@dataclass(frozen=True)
class SummaryReadinessQuery:
    user_id: str
    summary_type: SummaryType
    period_start: date | None = None


@dataclass(frozen=True)
class SummaryReadiness:
    """`GET /summaries/readiness` 응답용 DTO.

    측정 지표는 entry 밀도(완성도) — child summary 존재 여부가 아니다.
    monthly: expected = 그 달 일수, covered = entry 가 있는 날 수 (unique date_key)
    annual : expected = 12, covered = entry 가 있는 월 수
    """
    summary_type: SummaryType
    period_start: date
    period_end: date
    expected_units: int
    covered_units: int
    entry_count: int
    completeness_ratio: float
    recommendation: str  # "ok" | "insufficient"
