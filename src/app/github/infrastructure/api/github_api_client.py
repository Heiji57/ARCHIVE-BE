from dataclasses import dataclass

import httpx

from app.github.domain.exceptions.exceptions import (
    GitHubApiUnavailableException,
    GitHubRateLimitedException,
    GitHubRepositoryNotFoundException,
    GitHubTokenInvalidException,
)

_GITHUB_API = "https://api.github.com"
_PAGE_SIZE = 100
_MAX_PAGES = 20  # safety guard — 2000 repos cap


@dataclass(frozen=True)
class GitHubRepoData:
    github_repo_id: int
    owner: str
    name: str
    full_name: str
    is_private: bool
    default_branch: str
    html_url: str


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _parse(item: dict) -> GitHubRepoData:
    return GitHubRepoData(
        github_repo_id=int(item["id"]),
        owner=item["owner"]["login"],
        name=item["name"],
        full_name=item["full_name"],
        is_private=bool(item["private"]),
        default_branch=item.get("default_branch") or "main",
        html_url=item["html_url"],
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
    async def list_user_repositories(self, access_token: str) -> list[GitHubRepoData]:
        """Fetch authenticated user's public repos (paginated)."""
        results: list[GitHubRepoData] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, _MAX_PAGES + 1):
                response = await client.get(
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
                results.extend(_parse(item) for item in items)
                if len(items) < _PAGE_SIZE:
                    break
        return results

    async def get_repository(self, access_token: str, github_repo_id: int) -> GitHubRepoData:
        """Fetch a single repository by GitHub numeric ID."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{_GITHUB_API}/repositories/{github_repo_id}",
                headers=_headers(access_token),
            )
        _raise_for_status(response)
        return _parse(response.json())
