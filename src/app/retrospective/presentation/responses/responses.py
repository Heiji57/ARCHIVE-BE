from datetime import datetime

from pydantic import BaseModel, Field

from app.github.domain.models.retrospective_push import RetrospectivePush
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary


class GithubPushResponse(BaseModel):
    pushed_at: datetime = Field(serialization_alias="pushedAt")
    commit_sha: str = Field(serialization_alias="commitSha")
    html_url: str = Field(serialization_alias="htmlUrl")
    path: str
    repository_full_name: str = Field(serialization_alias="repositoryFullName")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, push: RetrospectivePush) -> "GithubPushResponse":
        return cls(
            pushed_at=push.pushed_at,
            commit_sha=push.commit_sha,
            html_url=push.html_url,
            path=push.path,
            repository_full_name=push.repository_full_name,
        )


class EntryResponse(BaseModel):
    """비개발자 또는 GitHub 미연결 사용자용 — githubPush 필드 없음."""

    id: str
    user_id: str
    date_key: str
    title: str
    content: str
    retro_type: str
    created_at: datetime
    updated_at: datetime | None
    # GET /entries/paginated 에서 weekly/monthly/annual 은 retro_summaries 기반이라
    # journal_entries 항목과 구분이 필요 — isSummary=true 면 status 도 함께 채워진다.
    is_summary: bool = Field(default=False, serialization_alias="isSummary")
    status: str | None = Field(default=None)
    folder_id: str | None = Field(default=None, serialization_alias="folderId")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, entry: JournalEntry) -> "EntryResponse":
        return cls(
            id=entry.id,
            user_id=entry.user_id,
            date_key=entry.date_key,
            title=entry.title,
            content=entry.content,
            retro_type=entry.retro_type.value,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            folder_id=entry.folder_id,
        )

    @classmethod
    def from_summary(cls, summary: RetroSummary) -> "EntryResponse":
        return cls(
            id=summary.id,
            user_id=summary.user_id,
            date_key=summary.period_start.isoformat(),
            # summary 는 title 이 없다 — 기간 기반 기본값. FE 가 원하면 자체 라벨로 대체.
            title=f"{summary.period_start.isoformat()} ~ {summary.period_end.isoformat()}",
            content=(
                summary.edited_content
                if summary.edited_content is not None
                else (summary.content.text if summary.content else "")
            ),
            retro_type=summary.summary_type.value,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            is_summary=True,
            status=summary.status.value,
            folder_id=summary.folder_id,
        )


class EntryWithGithubResponse(EntryResponse):
    """개발자 계정 + GitHub 연결 사용자용 — githubPush 포함."""

    github_push: GithubPushResponse | None = Field(
        default=None, serialization_alias="githubPush"
    )

    @classmethod
    def from_entity(  # type: ignore[override]
        cls,
        entry: JournalEntry,
        push: RetrospectivePush | None = None,
    ) -> "EntryWithGithubResponse":
        return cls(
            id=entry.id,
            user_id=entry.user_id,
            date_key=entry.date_key,
            title=entry.title,
            content=entry.content,
            retro_type=entry.retro_type.value,
            github_push=GithubPushResponse.from_entity(push) if push else None,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            folder_id=entry.folder_id,
        )

    @classmethod
    def from_summary(  # type: ignore[override]
        cls,
        summary: RetroSummary,
        push: RetrospectivePush | None = None,
    ) -> "EntryWithGithubResponse":
        base = EntryResponse.from_summary(summary)
        return cls(
            **base.model_dump(),
            github_push=GithubPushResponse.from_entity(push) if push else None,
        )


class EntryPageResponse(BaseModel):
    """GET /entries/paginated 응답 — 회고록 목록 페이지(최신순, 기본 10개씩)."""

    items: list[EntryWithGithubResponse]
    total: int
    page: int
    size: int

    model_config = {"populate_by_name": True}
