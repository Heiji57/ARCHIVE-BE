from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.retrospective.domain.exceptions.exceptions import (
    SummaryAlreadyInProgressException,
    SummaryInvalidStateException,
)
from app.retrospective.domain.models.value_objects import (
    SummaryContent,
    SummaryStatus,
    SummaryType,
)
from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class RetroSummary(BaseEntity):
    user_id: str
    summary_type: SummaryType
    period_start: date
    period_end: date
    status: SummaryStatus
    content: SummaryContent | None  # None — pending / in_progress / failed
    edited_content: str | None = None  # 사용자 편집 마크다운 오버라이드 (있으면 FE 가 우선 렌더)
    folder_id: str | None = None
    # 소스 없이 AI 호출을 건너뛴 요약 — 상위 요약(월간/연간)이 이 본문을 입력으로 쓰지 않는다.
    is_empty: bool = False

    def mark_in_progress(self) -> None:
        if self.status == SummaryStatus.IN_PROGRESS:
            raise SummaryAlreadyInProgressException()
        if self.status == SummaryStatus.COMPLETED:
            raise SummaryInvalidStateException("Already completed summary cannot restart.")
        self.status = SummaryStatus.IN_PROGRESS

    def complete(self, content: SummaryContent, *, is_empty: bool = False) -> None:
        """`is_empty` — 소스가 없어 AI 없이 안내 문구로 완료. 재생성 시 기본값이 해제한다."""
        self.status = SummaryStatus.COMPLETED
        self.content = content
        self.is_empty = is_empty

    def fail(self) -> None:
        self.status = SummaryStatus.FAILED

    def apply_edit(self, markdown: str | None) -> None:
        """사용자 편집 마크다운 저장. None 이면 편집 해제 → AI 원본(content) 으로 복귀."""
        self.edited_content = markdown
        self.updated_at = datetime.now(timezone.utc)
