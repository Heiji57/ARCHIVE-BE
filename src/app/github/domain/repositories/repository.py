from abc import ABC, abstractmethod

from app.github.domain.models.github_repository import GitHubRepository


class IGitHubRepositoryRepository(ABC):
    @abstractmethod
    async def save(self, repo: GitHubRepository) -> GitHubRepository: ...

    @abstractmethod
    async def save_many(self, repos: list[GitHubRepository]) -> list[GitHubRepository]: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> GitHubRepository | None: ...

    @abstractmethod
    async def find_by_user(self, user_id: str) -> list[GitHubRepository]: ...

    @abstractmethod
    async def find_commit_read_enabled_by_user(
        self, user_id: str
    ) -> list[GitHubRepository]: ...

    @abstractmethod
    async def find_by_github_id(
        self, user_id: str, github_repo_id: int
    ) -> GitHubRepository | None: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...

    @abstractmethod
    async def delete_all_by_user(self, user_id: str) -> None: ...
