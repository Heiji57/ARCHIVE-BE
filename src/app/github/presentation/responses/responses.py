from datetime import datetime

from pydantic import BaseModel, Field

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
