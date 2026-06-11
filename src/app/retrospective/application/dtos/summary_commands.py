from dataclasses import dataclass
from datetime import date

from app.retrospective.domain.models.value_objects import SummaryType


@dataclass
class RequestSummaryCommand:
    user_id: str
    summary_type: SummaryType
    period_start: date | None = None
    force: bool = False
