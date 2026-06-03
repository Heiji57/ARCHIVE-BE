from dataclasses import dataclass


@dataclass(frozen=True)
class LinkRepositoryCommand:
    user_id: str
    github_repo_id: int


@dataclass(frozen=True)
class SyncAllRepositoriesCommand:
    user_id: str


@dataclass(frozen=True)
class UnlinkRepositoryCommand:
    user_id: str
    repository_id: str
