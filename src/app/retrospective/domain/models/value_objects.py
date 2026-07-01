from dataclasses import dataclass
from enum import StrEnum


class RetroType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SummaryType(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SummaryStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class SummaryContent:
    """AI 생성 요약 마크다운 문자열. DB 에 TEXT 컬럼으로 저장된다."""
    text: str

    @classmethod
    def from_text(cls, text: str) -> "SummaryContent":
        return cls(text=text.strip() if text else "")
