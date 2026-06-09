from datetime import datetime

from pydantic import BaseModel, Field

from app.github.application.use_cases.get_connection_status import ConnectionStatus
from app.github.application.use_cases.get_commits_by_date import (
    CommitItem,
    CommitsByDateResult,
    FailedRepository,
)
from app.github.application.use_cases.push_retrospective import PushOutcome
from app.github.domain.models.github_repository import GitHubRepository
from app.github.infrastructure.api.github_api_client import GitHubRepoData


class RepositoryResponse(BaseModel):
    id: str
    github_repo_id: int = Field(serialization_alias="githubRepoId")
    owner: str
    name: str
    full_name: str = Field(serialization_alias="fullName")
    is_private: bool = Field(serialization_alias="isPrivate")
    default_branch: str = Field(serialization_alias="defaultBranch")
    html_url: str = Field(serialization_alias="htmlUrl")
    commit_read_enabled: bool = Field(serialization_alias="commitReadEnabled")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, repo: GitHubRepository) -> "RepositoryResponse":
        return cls(
            id=repo.id,
            github_repo_id=repo.github_repo_id,
            owner=repo.owner,
            name=repo.name,
            full_name=repo.full_name,
            is_private=repo.is_private,
            default_branch=repo.default_branch,
            html_url=repo.html_url,
            commit_read_enabled=repo.commit_read_enabled,
            created_at=repo.created_at,
            updated_at=repo.updated_at,
        )


class AvailableRepositoryResponse(BaseModel):
    github_repo_id: int = Field(serialization_alias="githubRepoId")
    owner: str
    name: str
    full_name: str = Field(serialization_alias="fullName")
    is_private: bool = Field(serialization_alias="isPrivate")
    default_branch: str = Field(serialization_alias="defaultBranch")
    html_url: str = Field(serialization_alias="htmlUrl")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_data(cls, data: GitHubRepoData) -> "AvailableRepositoryResponse":
        return cls(
            github_repo_id=data.github_repo_id,
            owner=data.owner,
            name=data.name,
            full_name=data.full_name,
            is_private=data.is_private,
            default_branch=data.default_branch,
            html_url=data.html_url,
        )


class ConnectionStatusResponse(BaseModel):
    connected: bool
    login: str | None = None
    push_target_repository_id: str | None = Field(
        default=None, serialization_alias="pushTargetRepositoryId"
    )
    has_verified_emails: bool = Field(serialization_alias="hasVerifiedEmails")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_status(cls, status: ConnectionStatus) -> "ConnectionStatusResponse":
        return cls(
            connected=status.connected,
            login=status.login,
            push_target_repository_id=status.push_target_repository_id,
            has_verified_emails=status.has_verified_emails,
        )


class CommitResponse(BaseModel):
    repository_id: str = Field(serialization_alias="repositoryId")
    full_name: str = Field(serialization_alias="fullName")
    sha: str
    message: str
    html_url: str = Field(serialization_alias="htmlUrl")
    author: str
    committed_at: datetime = Field(serialization_alias="committedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_commit(cls, c: CommitItem) -> "CommitResponse":
        return cls(
            repository_id=c.repository_id,
            full_name=c.full_name,
            sha=c.sha,
            message=c.message,
            html_url=c.html_url,
            author=c.author,
            committed_at=c.committed_at,
        )


class FailedRepositoryResponse(BaseModel):
    repository_id: str = Field(serialization_alias="repositoryId")
    full_name: str = Field(serialization_alias="fullName")
    reason: str  # 'not_found' | 'unknown'

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, f: FailedRepository) -> "FailedRepositoryResponse":
        return cls(
            repository_id=f.repository_id,
            full_name=f.full_name,
            reason=f.reason,
        )


class CommitListResponse(BaseModel):
    commits: list[CommitResponse]
    failed_repositories: list[FailedRepositoryResponse] = Field(
        serialization_alias="failedRepositories"
    )

    model_config = {"populate_by_name": True}

    @classmethod
    def from_result(cls, r: CommitsByDateResult) -> "CommitListResponse":
        return cls(
            commits=[CommitResponse.from_commit(c) for c in r.commits],
            failed_repositories=[
                FailedRepositoryResponse.from_entity(f) for f in r.failed_repositories
            ],
        )


class PushResultResponse(BaseModel):
    commit_sha: str = Field(serialization_alias="commitSha")
    html_url: str = Field(serialization_alias="htmlUrl")
    path: str

    model_config = {"populate_by_name": True}

    @classmethod
    def from_outcome(cls, o: PushOutcome) -> "PushResultResponse":
        return cls(commit_sha=o.commit_sha, html_url=o.html_url, path=o.path)
