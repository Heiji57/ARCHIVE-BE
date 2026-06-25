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

    def mark_in_progress(self) -> None:
        if self.status == SummaryStatus.IN_PROGRESS:
            raise SummaryAlreadyInProgressException()
        if self.status == SummaryStatus.COMPLETED:
            raise SummaryInvalidStateException("Already completed summary cannot restart.")
        self.status = SummaryStatus.IN_PROGRESS

    def complete(self, content: SummaryContent) -> None:
        self.status = SummaryStatus.COMPLETED
        self.content = content

    def fail(self) -> None:
        self.status = SummaryStatus.FAILED

    def apply_edit(self, markdown: str | None) -> None:
        """사용자 편집 마크다운 저장. None 이면 편집 해제 → AI 원본(content) 으로 복귀."""
        self.edited_content = markdown
        self.updated_at = datetime.now(timezone.utc)
