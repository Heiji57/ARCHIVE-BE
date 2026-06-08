"""사용자 tz 기준 특정 날짜의 커밋을 commit_read_enabled 저장소들에서 집계.

에러 분류 정책:
- **Fatal** (전체 raise): `GitHubTokenInvalidException`, `GitHubRateLimitedException`,
  `GitHubApiUnavailableException`. 토큰/제한/외부 가용성 문제는 사용자가 알아야 한다.
- **Per-repo** (skip + 로그 + failed list): `GitHubRepositoryNotFoundException` (삭제됨/
  private+scope 부족), 그 외 예기치 못한 예외. 다른 repo 결과는 정상 반환.

실패 repo 는 응답의 `failed_repositories` 로 사용자에게 노출 — silent skip 금지.
"""
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.application.use_cases._token import get_github_credentials
from app.github.domain.exceptions.exceptions import (
    GitHubApiUnavailableException,
    GitHubRateLimitedException,
    GitHubRepositoryNotFoundException,
    GitHubTokenInvalidException,
)
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.infrastructure.api.github_api_client import (
    GitHubApiClient,
    GitHubCommitData,
)
from app.shared.infrastructure.logger.security import get_security_logger
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class CommitItem:
    repository_id: str
    full_name: str
    sha: str
    message: str
    html_url: str
    author: str
    committed_at: datetime


@dataclass(frozen=True)
class FailedRepository:
    repository_id: str
    full_name: str
    reason: str        # 'not_found' | 'unknown'


@dataclass(frozen=True)
class CommitsByDateResult:
    commits: list[CommitItem]
    failed_repositories: list[FailedRepository]


class GetCommitsByDateUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        oauth_repo: IOAuthConnectionRepository,
        repo: IGitHubRepositoryRepository,
        api_client: GitHubApiClient,
    ) -> None:
        self._user_repo = user_repo
        self._oauth_repo = oauth_repo
        self._repo = repo
        self._api_client = api_client
        self._log = get_security_logger()

    async def execute(
        self,
        user_id: str,
        target_date: date | None = None,
    ) -> CommitsByDateResult:
        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise UserNotFoundException()

        tz = ZoneInfo(user.timezone)
        if target_date is None:
            target_date = datetime.now(tz).date()

        local_start = datetime.combine(target_date, time(0, 0), tz)
        local_end = datetime.combine(target_date + timedelta(days=1), time(0, 0), tz)
        since_iso = local_start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        until_iso = local_end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

        creds = await get_github_credentials(self._oauth_repo, self._api_client, user_id)
        repos = await self._repo.find_commit_read_enabled_by_user(user_id)
        if not repos:
            return CommitsByDateResult(commits=[], failed_repositories=[])

        async def fetch(repo) -> tuple[str, str, list[GitHubCommitData]]:
            commits = await self._api_client.list_commits(
                access_token=creds.access_token,
                owner=repo.owner,
                name=repo.name,
                since_iso=since_iso,
                until_iso=until_iso,
                author_login=creds.login,
            )
            return repo.id, repo.full_name, commits

        results = await asyncio.gather(
            *(fetch(r) for r in repos), return_exceptions=True
        )

        commits: list[CommitItem] = []
        failed: list[FailedRepository] = []

        for repo, r in zip(repos, results):
            if isinstance(r, (GitHubTokenInvalidException,
                              GitHubRateLimitedException,
                              GitHubApiUnavailableException)):
                raise r

            if isinstance(r, GitHubRepositoryNotFoundException):
                self._log.warning(
                    "github.commits.repo_not_found",
                    user_id=user_id,
                    repository_id=repo.id,
                    full_name=repo.full_name,
                )
                failed.append(
                    FailedRepository(
                        repository_id=repo.id,
                        full_name=repo.full_name,
                        reason="not_found",
                    )
                )
                continue

            if isinstance(r, Exception):
                self._log.warning(
                    "github.commits.unknown_error",
                    user_id=user_id,
                    repository_id=repo.id,
                    full_name=repo.full_name,
                    exception_type=type(r).__name__,
                    error=str(r),
                )
                failed.append(
                    FailedRepository(
                        repository_id=repo.id,
                        full_name=repo.full_name,
                        reason="unknown",
                    )
                )
                continue

            _, full_name, commit_list = r
            for c in commit_list:
                commits.append(
                    CommitItem(
                        repository_id=repo.id,
                        full_name=full_name,
                        sha=c.sha,
                        message=c.message,
                        html_url=c.html_url,
                        author=c.author,
                        committed_at=c.committed_at,
                    )
                )

        commits.sort(key=lambda x: x.committed_at, reverse=True)
        return CommitsByDateResult(commits=commits, failed_repositories=failed)
