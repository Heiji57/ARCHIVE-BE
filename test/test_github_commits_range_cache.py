"""기간 커밋 조회(`GET /github/commits?from=&to=`)와 날짜별 캐시.

- 저장소마다 캐시에 없는 날짜 구간만 GitHub 에서 한 번(branch 별)에 받고, 사용자 tz 날짜로
  나눠 빈 날까지 캐시한다. 오늘·어제는 짧게(5분), 그 이전은 24시간.
- 레이트 리밋은 저장소 단위 실패(`rate_limited`) — 캐시로 받은 날짜는 그대로 돌려준다.
"""
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

import app.github.application.use_cases.get_commits_by_date as mod
from app.github.application.use_cases.get_commits_by_date import (
    CommitItem,
    GetCommitsByDateUseCase,
)
from app.github.domain.exceptions.exceptions import (
    GitHubRateLimitedException,
    GitHubTokenInvalidException,
)
from app.github.infrastructure.api.github_api_client import GitHubCommitData

_TODAY = date(2026, 11, 16)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return datetime(2026, 11, 16, 12, 0, tzinfo=tz)


class _Cache:
    def __init__(self, seed=None) -> None:
        self.store: dict = dict(seed or {})
        self.ttl: dict = {}

    async def get_many(self, user_id, scope, keys):
        self.scope = scope
        return {k: self.store[k] for k in keys if k in self.store}

    async def set_many(self, user_id, scope, values, ttl_seconds):
        self.store.update(values)
        self.ttl.update(ttl_seconds)

    async def invalidate_user(self, user_id):
        self.store.clear()


def _commit(sha: str, when: datetime, login: str = "me") -> GitHubCommitData:
    return GitHubCommitData(
        sha=sha,
        message=sha,
        html_url=f"https://x/{sha}",
        author=login,
        committed_at=when,
        author_email=None,
        committer_email=None,
        author_login=login,
        committer_login=None,
    )


class _Api:
    def __init__(self, commits_by_repo: dict, fail: dict | None = None) -> None:
        self.commits_by_repo = commits_by_repo
        self.fail = fail or {}
        self.calls: list[tuple[str, str, str]] = []

    async def list_branches(self, access_token, owner, name):
        if name in self.fail:
            raise self.fail[name]
        return ["main", "dev"]

    async def list_commits(
        self, access_token, owner, name, since_iso, until_iso, author_login, sha
    ):
        self.calls.append((name, since_iso, until_iso))
        return [
            c
            for c in self.commits_by_repo.get(name, [])
            if since_iso <= c.committed_at.strftime("%Y-%m-%dT%H:%M:%SZ") < until_iso
        ]


class _Repos:
    def __init__(self, names):
        self._repos = [
            SimpleNamespace(id=f"repo_{n}", owner="o", name=n, full_name=f"o/{n}") for n in names
        ]

    async def find_commit_read_enabled_by_user(self, user_id):
        return self._repos


class _Users:
    async def find_by_id(self, user_id):
        return SimpleNamespace(timezone="Asia/Seoul")


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(mod, "datetime", _FrozenDatetime)

    async def creds(oauth_repo, api_client, user_id):
        return SimpleNamespace(access_token="t", login="me", verified_emails=[])

    monkeypatch.setattr(mod, "get_github_credentials", creds)


def _uc(api, cache, repos=("a",)):
    return GetCommitsByDateUseCase(_Users(), None, _Repos(repos), api, cache)  # type: ignore[arg-type]


async def test_range_groups_by_user_local_date_and_caches_empty_days():
    api = _Api({
        "a": [
            # KST 11-14 08:30 (UTC 11-13 23:30) — 로컬 날짜는 14일
            _commit("s1", datetime(2026, 11, 13, 23, 30, tzinfo=UTC)),
            _commit("s2", datetime(2026, 11, 15, 1, 0, tzinfo=UTC)),
            _commit("other", datetime(2026, 11, 15, 2, 0, tzinfo=UTC), login="someone"),
        ]
    })
    cache = _Cache()
    result = await _uc(api, cache).execute("usr_1", date(2026, 11, 13), date(2026, 11, 15))

    assert [(c.sha, c.date_key) for c in result.commits] == [
        ("s2", "2026-11-15"),
        ("s1", "2026-11-14"),
    ]
    # branch 마다 한 번 — 날짜마다가 아니다
    assert len(api.calls) == 2
    assert api.calls[0][1:] == ("2026-11-12T15:00:00Z", "2026-11-15T15:00:00Z")
    # 빈 날(13일)까지 캐시, 오늘·어제(15일)는 5분, 그 이전은 24시간
    assert cache.store[("repo_a", "2026-11-13")] == []
    assert cache.ttl[("repo_a", "2026-11-15")] == 300
    assert cache.ttl[("repo_a", "2026-11-14")] == 86400


async def test_fully_cached_range_does_not_call_github():
    hit = CommitItem(
        repository_id="repo_a",
        full_name="o/a",
        sha="cached",
        message="m",
        html_url="u",
        author="me",
        committed_at=datetime(2026, 11, 10, 3, tzinfo=UTC),
        date_key="2026-11-10",
    ).to_cache()
    cache = _Cache({("repo_a", "2026-11-10"): [hit], ("repo_a", "2026-11-11"): []})
    api = _Api({})
    result = await _uc(api, cache).execute("usr_1", date(2026, 11, 10), date(2026, 11, 11))
    assert api.calls == []
    assert [c.sha for c in result.commits] == ["cached"]
    assert result.commits[0].committed_at.tzinfo is not None


async def test_only_missing_span_is_fetched():
    cache = _Cache({("repo_a", "2026-11-10"): []})
    api = _Api({})
    await _uc(api, cache).execute("usr_1", date(2026, 11, 10), date(2026, 11, 12))
    # 11~12일만 (KST 경계 → UTC 10일 15시 ~ 12일 15시)
    assert api.calls[0][1:] == ("2026-11-10T15:00:00Z", "2026-11-12T15:00:00Z")


async def test_future_dates_are_not_queried():
    api = _Api({})
    result = await _uc(api, _Cache()).execute("usr_1", date(2026, 11, 20), date(2026, 11, 22))
    assert result.commits == [] and api.calls == []


async def test_rate_limit_is_per_repo_failure_and_keeps_others():
    api = _Api(
        {"b": [_commit("ok", datetime(2026, 11, 15, 1, tzinfo=UTC))]},
        fail={"a": GitHubRateLimitedException()},
    )
    result = await _uc(api, _Cache(), repos=("a", "b")).execute(
        "usr_1", date(2026, 11, 15), date(2026, 11, 15)
    )
    assert [c.sha for c in result.commits] == ["ok"]
    failed = [(f.full_name, f.reason) for f in result.failed_repositories]
    assert failed == [("o/a", "rate_limited")]


async def test_token_invalid_is_still_fatal():
    api = _Api({}, fail={"a": GitHubTokenInvalidException()})
    with pytest.raises(GitHubTokenInvalidException):
        await _uc(api, _Cache()).execute("usr_1", date(2026, 11, 15), date(2026, 11, 15))


async def test_router_rejects_range_over_31_days_and_mixed_params():
    from app.github.domain.exceptions.exceptions import (
        GitHubCommitQueryInvalidException,
        GitHubRangeTooLongException,
    )
    from app.github.presentation.router import get_commits

    user = SimpleNamespace(id="usr_1")
    with pytest.raises(GitHubRangeTooLongException):
        await get_commits(None, None, date(2026, 10, 1), date(2026, 11, 1), user)  # type: ignore[arg-type]
    with pytest.raises(GitHubCommitQueryInvalidException):
        await get_commits(None, date(2026, 11, 1), date(2026, 11, 1), date(2026, 11, 2), user)  # type: ignore[arg-type]
    with pytest.raises(GitHubCommitQueryInvalidException):
        await get_commits(None, None, date(2026, 11, 2), date(2026, 11, 1), user)  # type: ignore[arg-type]
    with pytest.raises(GitHubCommitQueryInvalidException):
        await get_commits(None, None, date(2026, 11, 2), None, user)  # type: ignore[arg-type]


async def test_cache_scope_includes_timezone_and_login():
    cache = _Cache()
    await _uc(_Api({}), cache).execute("usr_1", date(2026, 11, 15), date(2026, 11, 15))
    assert cache.scope == "Asia/Seoul|me"


async def test_truncated_span_is_returned_but_not_cached(monkeypatch):
    monkeypatch.setattr(mod, "COMMITS_FETCH_CAP", 2)
    api = _Api({
        "a": [
            _commit("c1", datetime(2026, 11, 15, 1, tzinfo=UTC)),
            _commit("c2", datetime(2026, 11, 15, 2, tzinfo=UTC)),
        ]
    })
    cache = _Cache()
    result = await _uc(api, cache).execute("usr_1", date(2026, 11, 14), date(2026, 11, 15))
    assert {c.sha for c in result.commits} == {"c1", "c2"}
    assert cache.store == {}


async def test_unreadable_cached_payload_is_a_miss():
    cache = _Cache({("repo_a", "2026-11-15"): [{"sha": "old-shape"}]})
    api = _Api({"a": [_commit("fresh", datetime(2026, 11, 15, 1, tzinfo=UTC))]})
    result = await _uc(api, cache).execute("usr_1", date(2026, 11, 15), date(2026, 11, 15))
    assert [c.sha for c in result.commits] == ["fresh"]
    assert len(api.calls) == 2
