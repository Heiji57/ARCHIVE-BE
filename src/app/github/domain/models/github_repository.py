from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class GitHubRepository(BaseEntity):
    user_id: str
    github_repo_id: int
    owner: str
    name: str
    full_name: str
    is_private: bool
    default_branch: str
    html_url: str
    commit_read_enabled: bool = True
