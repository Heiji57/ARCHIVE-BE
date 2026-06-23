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
    """템플릿 유무에 따라 섹션 키가 달라지므로 dict로 관리.

    기존 DB 레코드(achievements/challenges/learnings/next_focus)도
    from_dict 로 그대로 로드된다.
    """
    sections: dict[str, list[str]]

    def to_dict(self) -> dict[str, list[str]]:
        return dict(self.sections)

    @classmethod
    def from_dict(cls, data: dict) -> "SummaryContent":
        return cls(
            sections={
                k: [str(i) for i in v if i is not None]
                for k, v in data.items()
                if isinstance(v, list)
            }
        )
