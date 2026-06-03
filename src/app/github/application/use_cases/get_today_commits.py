"""사용자 tz 기준 특정 날짜의 커밋 모음을 commit_read_enabled 저장소들에서 집계."""
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.application.use_cases._token import get_github_access_token
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.infrastructure.api.github_api_client import (
    GitHubApiClient,
    GitHubCommitData,
)
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class TodayCommit:
    repository_id: str
    full_name: str
    sha: str
    message: str
    html_url: str
    author: str
    committed_at: datetime


class GetTodayCommitsUseCase:
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

    async def execute(
        self,
        user_id: str,
        target_date: date | None = None,
    ) -> list[TodayCommit]:
        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise UserNotFoundException()

        tz = ZoneInfo(user.timezone)
        if target_date is None:
            target_date = datetime.now(tz).date()

        # [target_date 00:00, target_date+1 00:00) 사용자 tz → UTC ISO
        local_start = datetime.combine(target_date, time(0, 0), tz)
        local_end = datetime.combine(target_date + timedelta(days=1), time(0, 0), tz)
        since_iso = local_start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        until_iso = local_end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

        access_token = await get_github_access_token(self._oauth_repo, user_id)
        repos = await self._repo.find_commit_read_enabled_by_user(user_id)
        if not repos:
            return []

        # 작성자 본인의 커밋만 (author=login)
        authenticated = await self._api_client.get_authenticated_user(access_token)

        async def fetch(repo) -> tuple[str, str, list[GitHubCommitData]]:
            commits = await self._api_client.list_commits(
                access_token=access_token,
                owner=repo.owner,
                name=repo.name,
                since_iso=since_iso,
                until_iso=until_iso,
                author_login=authenticated.login,
            )
            return repo.id, repo.full_name, commits

        results = await asyncio.gather(*(fetch(r) for r in repos), return_exceptions=True)

        out: list[TodayCommit] = []
        for r in results:
            if isinstance(r, Exception):
                # 단일 저장소 실패는 무시하고 나머지 결과만 반환 (rate limit 등은 raise됨)
                continue
            repo_id, full_name, commits = r
            for c in commits:
                out.append(
                    TodayCommit(
                        repository_id=repo_id,
                        full_name=full_name,
                        sha=c.sha,
                        message=c.message,
                        html_url=c.html_url,
                        author=c.author,
                        committed_at=c.committed_at,
                    )
                )

        out.sort(key=lambda x: x.committed_at, reverse=True)
        return out
