from dataclasses import dataclass
from enum import StrEnum


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
    achievements: tuple[str, ...]
    challenges: tuple[str, ...]
    learnings: tuple[str, ...]
    next_focus: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "achievements": list(self.achievements),
            "challenges": list(self.challenges),
            "learnings": list(self.learnings),
            "next_focus": list(self.next_focus),
        }

    @classmethod
    def from_dict(cls, data: dict[str, list[str]]) -> "SummaryContent":
        return cls(
            achievements=tuple(data.get("achievements", [])),
            challenges=tuple(data.get("challenges", [])),
            learnings=tuple(data.get("learnings", [])),
            next_focus=tuple(data.get("next_focus", [])),
        )
