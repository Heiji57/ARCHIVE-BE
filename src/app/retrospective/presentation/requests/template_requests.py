from pydantic import BaseModel, Field


class CreateSummaryTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)

    model_config = {"populate_by_name": True}


class UpdateSummaryTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)

    model_config = {"populate_by_name": True}


class SetActiveSummaryTemplatesRequest(BaseModel):
    """summary_type 별 활성 템플릿 ID 부분 갱신.

    필드별 의미:
    - 문자열      → 해당 type 의 활성 ID 로 설정 (소유 / type 일치 검증)
    - 명시적 null → 해당 type 비활성화 (시스템 기본 사용)
    - 미전송      → 변경 없음

    Pydantic 의 model_fields_set 으로 "전송 여부" 구분.
    """
    weekly: str | None = Field(default=None)
    monthly: str | None = Field(default=None)
    annual: str | None = Field(default=None)

    model_config = {"populate_by_name": True}

    def to_selections(self) -> dict[str, str | None]:
        """실제 전송된 필드만 dict 로 추출."""
        sent = self.model_fields_set
        result: dict[str, str | None] = {}
        if "weekly" in sent:
            result["weekly"] = self.weekly
        if "monthly" in sent:
            result["monthly"] = self.monthly
        if "annual" in sent:
            result["annual"] = self.annual
        return result
