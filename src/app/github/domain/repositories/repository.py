from abc import ABC, abstractmethod
from typing import Any

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


class ICommitDayCache(ABC):
    """사용자·저장소·날짜(사용자 tz) 단위 커밋 캐시. 값은 그날 본인 커밋의 직렬화 목록.

    `scope` 는 값이 기대는 조건(사용자 tz, GitHub login)이다 — 키에 섞어, tz 를 바꾸거나
    다른 GitHub 계정을 연결하면 별도 무효화 없이 다른 키를 쓴다.
    캐시는 부가 수단이다 — 구현체는 저장소 장애·깨진 값을 예외 대신 "없음"으로 응답한다.
    """

    @abstractmethod
    async def get_many(
        self, user_id: str, scope: str, keys: list[tuple[str, str]]
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """(repository_id, date_key) 목록 → 캐시에 있는 것만."""
        ...

    @abstractmethod
    async def set_many(
        self,
        user_id: str,
        scope: str,
        values: dict[tuple[str, str], list[dict[str, Any]]],
        ttl_seconds: dict[tuple[str, str], int],
    ) -> None: ...

    @abstractmethod
    async def invalidate_user(self, user_id: str) -> None:
        """저장소 연결·커밋 읽기 설정이 바뀌면 그 사용자 캐시 전체를 지운다."""
        ...
