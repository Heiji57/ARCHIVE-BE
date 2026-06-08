import base64
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.github.domain.exceptions.exceptions import (
    GitHubApiUnavailableException,
    GitHubPushFailedException,
    GitHubRateLimitedException,
    GitHubRepositoryNotFoundException,
    GitHubTokenInvalidException,
)

_GITHUB_API = "https://api.github.com"
_PAGE_SIZE = 100
_MAX_PAGES = 20  # safety guard — 2000 repos cap
_COMMITS_PAGE_SIZE = 100
_COMMITS_MAX_PAGES = 5  # 500 commits per repo per day max

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


@dataclass(frozen=True)
class GitHubRepoData:
    github_repo_id: int
    owner: str
    name: str
    full_name: str
    is_private: bool
    default_branch: str
    html_url: str


@dataclass(frozen=True)
class GitHubCommitData:
    sha: str
    message: str
    html_url: str
    author: str
    committed_at: datetime


@dataclass(frozen=True)
class GitHubAuthenticatedUser:
    login: str


@dataclass(frozen=True)
class GitHubPushResult:
    commit_sha: str
    html_url: str
    path: str


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _parse_repo(item: dict) -> GitHubRepoData:
    return GitHubRepoData(
        github_repo_id=int(item["id"]),
        owner=item["owner"]["login"],
        name=item["name"],
        full_name=item["full_name"],
        is_private=bool(item["private"]),
        default_branch=item.get("default_branch") or "main",
        html_url=item["html_url"],
    )


def _parse_commit(item: dict) -> GitHubCommitData:
    commit = item["commit"]
    author = commit.get("author", {}) or {}
    committed_at_raw = author.get("date") or commit.get("committer", {}).get("date")
    committed_at = datetime.fromisoformat(committed_at_raw.replace("Z", "+00:00"))
    author_login = (item.get("author") or {}).get("login") or author.get("name") or "unknown"
    return GitHubCommitData(
        sha=item["sha"],
        message=(commit.get("message") or "").splitlines()[0][:200],
        html_url=item["html_url"],
        author=author_login,
        committed_at=committed_at,
    )


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise GitHubTokenInvalidException()
    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        raise GitHubRateLimitedException()
    if response.status_code == 404:
        raise GitHubRepositoryNotFoundException()
    if response.status_code >= 500:
        raise GitHubApiUnavailableException()
    if response.status_code >= 400:
        raise GitHubApiUnavailableException()


class GitHubApiClient:
    """단일 long-lived httpx.AsyncClient 를 재사용 — 커넥션 풀링.

    APP scope 로 dishka 등록. lifespan 종료 시 `close()` 호출.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def close(self) -> None:
        await self._client.aclose()

    async def list_user_repositories(self, access_token: str) -> list[GitHubRepoData]:
        results: list[GitHubRepoData] = []
        for page in range(1, _MAX_PAGES + 1):
            response = await self._client.get(
                f"{_GITHUB_API}/user/repos",
                headers=_headers(access_token),
                params={
                    "per_page": _PAGE_SIZE,
                    "page": page,
                    "visibility": "public",
                    "affiliation": "owner,collaborator",
                    "sort": "full_name",
                },
            )
            _raise_for_status(response)
            items = response.json()
            if not items:
                break
            results.extend(_parse_repo(item) for item in items)
            if len(items) < _PAGE_SIZE:
                break
        return results

    async def get_repository(self, access_token: str, github_repo_id: int) -> GitHubRepoData:
        response = await self._client.get(
            f"{_GITHUB_API}/repositories/{github_repo_id}",
            headers=_headers(access_token),
        )
        _raise_for_status(response)
        return _parse_repo(response.json())

    async def get_authenticated_user(self, access_token: str) -> GitHubAuthenticatedUser:
        response = await self._client.get(
            f"{_GITHUB_API}/user",
            headers=_headers(access_token),
        )
        _raise_for_status(response)
        data = response.json()
        return GitHubAuthenticatedUser(login=data["login"])

    async def list_commits(
        self,
        access_token: str,
        owner: str,
        name: str,
        since_iso: str,
        until_iso: str,
        author_login: str | None = None,
    ) -> list[GitHubCommitData]:
        """List commits in [since, until) — caller must format ISO 8601 UTC strings."""
        results: list[GitHubCommitData] = []
        for page in range(1, _COMMITS_MAX_PAGES + 1):
            params: dict[str, str | int] = {
                "since": since_iso,
                "until": until_iso,
                "per_page": _COMMITS_PAGE_SIZE,
                "page": page,
            }
            if author_login:
                params["author"] = author_login
            response = await self._client.get(
                f"{_GITHUB_API}/repos/{owner}/{name}/commits",
                headers=_headers(access_token),
                params=params,
            )
            # 빈 저장소 등으로 409가 올 수 있음 → 정상 처리
            if response.status_code == 409:
                break
            _raise_for_status(response)
            items = response.json()
            if not items:
                break
            results.extend(_parse_commit(item) for item in items)
            if len(items) < _COMMITS_PAGE_SIZE:
                break
        return results

    async def get_file_sha(
        self,
        access_token: str,
        owner: str,
        name: str,
        path: str,
        branch: str,
    ) -> str | None:
        """Returns sha if file exists, None if 404."""
        response = await self._client.get(
            f"{_GITHUB_API}/repos/{owner}/{name}/contents/{path}",
            headers=_headers(access_token),
            params={"ref": branch},
        )
        if response.status_code == 404:
            return None
        if response.status_code == 401:
            raise GitHubTokenInvalidException()
        if response.status_code >= 400:
            raise GitHubApiUnavailableException()
        return response.json().get("sha")

    async def put_file(
        self,
        access_token: str,
        owner: str,
        name: str,
        path: str,
        content_bytes: bytes,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> GitHubPushResult:
        """Create or update file via Contents API. Pass sha for update, omit for create."""
        body: dict = {
            "message": message,
            "content": base64.b64encode(content_bytes).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        response = await self._client.put(
            f"{_GITHUB_API}/repos/{owner}/{name}/contents/{path}",
            headers=_headers(access_token),
            json=body,
        )

        if response.status_code == 401:
            raise GitHubTokenInvalidException()
        if response.status_code == 404:
            raise GitHubRepositoryNotFoundException()
        if response.status_code == 409 or response.status_code == 422:
            # conflict (sha mismatch) or invalid request
            raise GitHubPushFailedException(
                f"GitHub returned {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 500:
            raise GitHubApiUnavailableException()
        if response.status_code not in (200, 201):
            raise GitHubPushFailedException(
                f"GitHub returned {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        commit = data.get("commit", {})
        content = data.get("content", {})
        return GitHubPushResult(
            commit_sha=commit.get("sha", ""),
            html_url=content.get("html_url") or commit.get("html_url", ""),
            path=content.get("path") or path,
        )
