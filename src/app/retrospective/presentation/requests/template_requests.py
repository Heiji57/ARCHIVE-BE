from pydantic import BaseModel, Field


class CreateSummaryTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # content 는 빈 문자열 허용 (스펙: 0~4000자) — min_length 제약 없음
    content: str = Field(max_length=4000)

    model_config = {"populate_by_name": True}


class UpdateSummaryTemplateRequest(BaseModel):
    # PATCH 부분 수정 — 전송된 필드만 갱신 (회고 템플릿 PATCH 와 동일 관례).
    # name="" 은 422(빈 이름 금지), content="" 은 허용(빈 본문으로 클리어).
    name: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, max_length=4000)

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
