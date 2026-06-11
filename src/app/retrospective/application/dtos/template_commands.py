from dataclasses import dataclass

from app.retrospective.domain.models.value_objects import SummaryType


@dataclass(frozen=True)
class CreateSummaryTemplateCommand:
    user_id: str
    summary_type: SummaryType
    name: str
    content: str


@dataclass(frozen=True)
class UpdateSummaryTemplateCommand:
    user_id: str
    template_id: str
    name: str
    content: str


@dataclass(frozen=True)
class DeleteSummaryTemplateCommand:
    user_id: str
    template_id: str


@dataclass(frozen=True)
class SetActiveSummaryTemplateCommand:
    """summary_type 별 활성 템플릿 ID 부분 갱신.

    각 필드:
    - 문자열 → 해당 summary_type 의 활성 ID 로 설정 (소유·타입 검증)
    - None  → "변경 없음" 이 아닌 "비활성화 / 시스템 기본 사용" 으로 해석되게
              하려면 별도 sentinel 이 필요. 여기서는 단순화 위해 Request 가 명시한
              필드만 cmd 에 담아 보내고, 빠진 필드는 변경 안 함.
    """
    user_id: str
    # summary_type 명(string) → template_id 또는 None(비활성). 키 부재면 변경 안 함.
    selections: dict[str, str | None]
