from datetime import datetime

from pydantic import BaseModel, Field

from app.github.domain.models.retrospective_push import RetrospectivePush
from app.retrospective.domain.models.journal_entry import JournalEntry


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
        )
