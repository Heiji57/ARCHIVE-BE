from dataclasses import dataclass

from app.retrospective.domain.models.value_objects import SummaryType
from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class UserSummaryTemplate(BaseEntity):
    """사용자가 정의한 AI 자동 요약 markdown 템플릿.

    (user_id, summary_type, name) 은 유니크 — DB 인덱스로 강제.
    한 (user, summary_type) 당 개수 한도는 use case 가 검증
    (env: SUMMARY_TEMPLATE_MAX_PER_TYPE).
    """
    user_id: str
    summary_type: SummaryType
    name: str        # 사용자 식별용
    content: str     # markdown body (max 4000 — Pydantic 에서 검증)
