"""사용자 tz 기준 날짜(또는 기간, 최대 31일)의 커밋을 commit_read_enabled 저장소들에서 집계.

캐시 (`ICommitDayCache`, 저장소 × 사용자 tz 날짜 단위):
- 캐시에 없는 날짜가 있는 저장소만 GitHub 를 부른다. 그 저장소의 빠진 날짜 구간
  [최소, 최대]를 branch 마다 한 번에 받아 로컬 날짜로 나눈 뒤, 구간의 모든 날짜(빈 날 포함)를
  캐시에 쓴다. 오늘·어제는 5분(아직 커밋이 쌓임), 그 이전은 24시간.
- 저장소 연결·커밋 읽기 설정이 바뀌면 라우터가 그 사용자 캐시를 지운다.
- 오늘 이후 날짜는 조회하지 않는다(커밋이 있을 수 없다).

조회 범위 (Phase 2):
- 저장소의 **모든 branch** 의 commit 을 조회 (default branch 제한 없음).
- 각 repo: list_branches 로 branch 목록 fetch → branch 별 list_commits 병렬 호출
  → 모든 결과를 commit sha 로 dedup.

매칭 정책:
- GitHub `?author=` 필터는 사용 안 함 — 그 repo 의 모든 commit 을 일단 받음
- 서버사이드 필터: 다음 중 하나라도 매칭되면 본인 commit 으로 간주
    1. commit author 의 GitHub login 이 `creds.login`
    2. commit committer 의 GitHub login 이 `creds.login`
    3. commit author email 이 `creds.verified_emails` 에 포함
    4. commit committer email 이 `creds.verified_emails` 에 포함
- 이 정책으로 gitbash 등 로컬 git config email 이 GitHub 계정에 verified 등록돼
  있으면 본인 commit 으로 잡힌다.

에러 분류 정책:
- **Fatal** (전체 raise): `GitHubTokenInvalidException`, `GitHubApiUnavailableException`.
  토큰/외부 가용성 문제는 사용자가 알아야 한다.
- **Per-repo** (skip + 로그 + failed list): `GitHubRepositoryNotFoundException` (삭제됨/
  private+scope 부족) → `not_found`, `GitHubRateLimitedException` → `rate_limited`
  (캐시로 받은 날짜는 그대로 돌려준다), 그 외 예기치 못한 예외 → `unknown`.

실패 repo 는 응답의 `failed_repositories` 로 사용자에게 노출 — silent skip 금지.
"""
import asyncio
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.application.use_cases._token import get_github_credentials
from app.github.domain.exceptions.exceptions import (
    GitHubApiUnavailableException,
    GitHubRateLimitedException,
    GitHubRepositoryNotFoundException,
    GitHubTokenInvalidException,
)
from app.github.domain.repositories.repository import ICommitDayCache, IGitHubRepositoryRepository
from app.github.infrastructure.api.github_api_client import (
    COMMITS_FETCH_CAP,
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
    date_key: str  # 사용자 tz 기준 커밋 날짜 — FE 가 이 값으로 묶는다

    def to_cache(self) -> dict[str, Any]:
        d = asdict(self)
        d["committed_at"] = self.committed_at.isoformat()
        return d

    @classmethod
    def from_cache(cls, d: dict[str, Any]) -> "CommitItem":
        return cls(**{**d, "committed_at": datetime.fromisoformat(d["committed_at"])})


@dataclass(frozen=True)
class FailedRepository:
    repository_id: str
    full_name: str
    reason: str  # 'not_found' | 'rate_limited' | 'unknown'


@dataclass(frozen=True)
class CommitsByDateResult:
    commits: list[CommitItem]
    failed_repositories: list[FailedRepository]


_FATAL_EXCEPTIONS = (
    GitHubTokenInvalidException,
    GitHubApiUnavailableException,
)

MAX_RANGE_DAYS = 31
_RECENT_TTL_SECONDS = 5 * 60  # 오늘·어제 — 아직 커밋이 쌓인다
_PAST_TTL_SECONDS = 24 * 60 * 60


def _days(from_date: date, to_date: date) -> list[date]:
    return [from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)]


def _is_user_commit(
    commit: GitHubCommitData,
    github_login: str,
    verified_emails: set[str],
) -> bool:
    """본인 commit 판정 — login 또는 verified email 매칭."""
    if commit.author_login == github_login:
        return True
    if commit.committer_login == github_login:
        return True
    if commit.author_email and commit.author_email in verified_emails:
        return True
    if commit.committer_email and commit.committer_email in verified_emails:
        return True
    return False


class GetCommitsByDateUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        oauth_repo: IOAuthConnectionRepository,
        repo: IGitHubRepositoryRepository,
        api_client: GitHubApiClient,
        cache: ICommitDayCache,
    ) -> None:
        self._user_repo = user_repo
        self._oauth_repo = oauth_repo
        self._repo = repo
        self._api_client = api_client
        self._cache = cache
        self._log = get_security_logger()

    async def execute(
        self,
        user_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> CommitsByDateResult:
        """[from_date, to_date] (사용자 tz, 포함). 둘 다 없으면 오늘, to 가 없으면 from 하루."""
        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise UserNotFoundException()

        tz = ZoneInfo(user.timezone)
        today = datetime.now(tz).date()
        from_date = from_date or today
        to_date = min(to_date or from_date, today)
        days = _days(from_date, to_date) if from_date <= to_date else []

        # 연결 확인(없으면 GITHUB_CONNECTION_NOT_FOUND)은 캐시와 무관하게 항상 한다.
        creds = await get_github_credentials(self._oauth_repo, self._api_client, user_id)
        verified_emails_set = set(creds.verified_emails)

        repos = await self._repo.find_commit_read_enabled_by_user(user_id)
        if not repos or not days:
            return CommitsByDateResult(commits=[], failed_repositories=[])

        day_keys = [d.isoformat() for d in days]
        scope = f"{user.timezone}|{creds.login}"
        raw_cached = await self._cache.get_many(
            user_id, scope, [(r.id, k) for r in repos for k in day_keys]
        )
        # 모양이 바뀐 옛 값 등 읽을 수 없는 항목은 미스로 본다.
        cached: dict[tuple[str, str], list[CommitItem]] = {}
        for key, payload in raw_cached.items():
            try:
                cached[key] = [CommitItem.from_cache(c) for c in payload]
            except (KeyError, TypeError, ValueError):
                continue

        async def fetch_span(
            repo, start: date, end: date
        ) -> tuple[dict[str, list[CommitItem]], bool]:
            """한 repo 의 [start, end] 구간을 모든 branch 에서 받아 로컬 날짜별로 나눈다.

            두 번째 값은 "잘렸을 수 있음" — branch 하나라도 호출 상한만큼 받았으면 구간의
            오래된 쪽 커밋이 빠졌을 수 있으므로 캐시하지 않는다.
            """
            local_start = datetime.combine(start, time(0, 0), tz)
            local_end = datetime.combine(end + timedelta(days=1), time(0, 0), tz)
            since_iso = local_start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
            until_iso = local_end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

            by_day: dict[str, list[CommitItem]] = {d.isoformat(): [] for d in _days(start, end)}
            branches = await self._api_client.list_branches(
                access_token=creds.access_token,
                owner=repo.owner,
                name=repo.name,
            )
            if not branches:
                return by_day, False

            branch_results = await asyncio.gather(
                *(
                    self._api_client.list_commits(
                        access_token=creds.access_token,
                        owner=repo.owner,
                        name=repo.name,
                        since_iso=since_iso,
                        until_iso=until_iso,
                        author_login=None,
                        sha=branch,
                    )
                    for branch in branches
                ),
                return_exceptions=True,
            )

            seen: dict[str, GitHubCommitData] = {}
            truncated = False
            for r in branch_results:
                if isinstance(r, BaseException):
                    # branch 단위 실패는 repo 전체 실패로 격상 — 상위 핸들러가 처리
                    raise r
                truncated = truncated or len(r) >= COMMITS_FETCH_CAP
                for c in r:
                    if c.sha not in seen:
                        seen[c.sha] = c

            for c in seen.values():
                if not _is_user_commit(c, creds.login, verified_emails_set):
                    continue
                day = c.committed_at.astimezone(tz).date().isoformat()
                if day not in by_day:
                    continue  # GitHub since/until 경계 밖(시계 오차 등)
                by_day[day].append(
                    CommitItem(
                        repository_id=repo.id,
                        full_name=repo.full_name,
                        sha=c.sha,
                        message=c.message,
                        html_url=c.html_url,
                        author=c.author,
                        committed_at=c.committed_at,
                        date_key=day,
                    )
                )
            return by_day, truncated

        to_fetch: list[tuple[Any, date, date]] = []
        for repo in repos:
            missing = [d for d in days if (repo.id, d.isoformat()) not in cached]
            if missing:
                to_fetch.append((repo, min(missing), max(missing)))

        results = await asyncio.gather(
            *(fetch_span(repo, start, end) for repo, start, end in to_fetch),
            return_exceptions=True,
        )

        commits: list[CommitItem] = [c for items in cached.values() for c in items]
        failed: list[FailedRepository] = []
        to_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        ttl: dict[tuple[str, str], int] = {}
        recent_cutoff = (today - timedelta(days=1)).isoformat()

        for (repo, _, _), r in zip(to_fetch, results):
            if isinstance(r, _FATAL_EXCEPTIONS):
                raise r

            reason = None
            if isinstance(r, GitHubRepositoryNotFoundException):
                reason = "not_found"
            elif isinstance(r, GitHubRateLimitedException):
                reason = "rate_limited"
            elif isinstance(r, BaseException):
                reason = "unknown"
            if reason is not None:
                self._log.warning(
                    "github.commits.repo_failed",
                    user_id=user_id,
                    repository_id=repo.id,
                    full_name=repo.full_name,
                    reason=reason,
                    exception_type=type(r).__name__,
                    error=str(r),
                )
                failed.append(
                    FailedRepository(repository_id=repo.id, full_name=repo.full_name, reason=reason)
                )
                continue

            assert isinstance(r, tuple)
            by_day, truncated = r
            if truncated:
                self._log.warning(
                    "github.commits.span_truncated",
                    user_id=user_id,
                    repository_id=repo.id,
                    cap=COMMITS_FETCH_CAP,
                )
            for day, items in by_day.items():
                key = (repo.id, day)
                # 구간 안에 이미 캐시된 날이 있어도 방금 받은 값이 더 새롭다 — 덮어쓴다.
                if key in cached:
                    commits = [
                        c for c in commits if not (c.repository_id == repo.id and c.date_key == day)
                    ]
                commits.extend(items)
                if not truncated:
                    to_cache[key] = [c.to_cache() for c in items]
                    ttl[key] = _RECENT_TTL_SECONDS if day >= recent_cutoff else _PAST_TTL_SECONDS

        await self._cache.set_many(user_id, scope, to_cache, ttl)
        commits.sort(key=lambda x: x.committed_at, reverse=True)
        return CommitsByDateResult(commits=commits, failed_repositories=failed)
