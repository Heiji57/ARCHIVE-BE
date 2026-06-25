from dataclasses import dataclass
from datetime import date

from app.retrospective.domain.models.value_objects import SummaryType


@dataclass
class RequestSummaryCommand:
    user_id: str
    summary_type: SummaryType
    period_start: date | None = None
    force: bool = False


@dataclass
class EditSummaryCommand:
    user_id: str
    summary_id: str
    content_markdown: str | None  # None — 편집 해제(AI 원본 복귀)
