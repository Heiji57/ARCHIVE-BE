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
    id: str
    user_id: str
    date_key: str
    title: str
    content: str
    retro_type: str
    github_push: GithubPushResponse | None = Field(
        default=None, serialization_alias="githubPush"
    )
    created_at: datetime
    updated_at: datetime | None

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(
        cls,
        entry: JournalEntry,
        push: RetrospectivePush | None = None,
    ) -> "EntryResponse":
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
