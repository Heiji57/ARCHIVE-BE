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

    메모리 내 표현은 삽입 순서가 보존되는 dict.
    JSONB 저장 시 키 순서가 깨지는 문제를 막기 위해 배열 형태로 직렬화한다:
      {"sections": [{"key": "한 일", "items": [...]}, ...]}
    구 행(flat dict 형태) 역직렬화도 from_dict 에서 처리한다.
    """
    sections: dict[str, list[str]]

    def to_dict(self) -> dict:
        return {
            "sections": [
                {"key": k, "items": v} for k, v in self.sections.items()
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SummaryContent":
        # 신규 배열 형식: {"sections": [{"key": ..., "items": [...]}, ...]}
        if isinstance(data.get("sections"), list):
            return cls(
                sections={
                    entry["key"]: [str(i) for i in entry.get("items", []) if i is not None]
                    for entry in data["sections"]
                    if isinstance(entry, dict) and "key" in entry
                }
            )
        # 레거시 flat dict 형식: {"achievements": [...], ...}
        return cls(
            sections={
                k: [str(i) for i in v if i is not None]
                for k, v in data.items()
                if isinstance(v, list)
            }
        )
