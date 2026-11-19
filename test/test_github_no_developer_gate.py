"""개발자/일반 계정 구분 제거 — GitHub 기능은 GitHub 연결 여부로만 판단한다.

- GitHub 라우트는 인증만 요구한다(예전 `_require_developer` → 403 DEVELOPER_ACCOUNT_REQUIRED 없음).
- access token 에 account_type 클레임이 없다.
- 회고 조회는 GitHub 이 연결돼 있으면 계정 종류와 무관하게 push 정보를 붙인다.
"""
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.routing import APIRoute
from jose import jwt

from app.auth.domain.models.oauth_connection import OAuthConnection
from app.auth.domain.models.value_objects import OAuthProvider
from app.github.presentation.router import router as github_router
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.presentation.router import get_entry
from app.shared.infrastructure.auth.jwt import create_access_token, get_current_user
from app.shared.infrastructure.config.settings import get_settings


def _dependency_calls(dependant) -> set:
    calls = {dependant.call}
    for sub in dependant.dependencies:
        calls |= _dependency_calls(sub)
    return calls


def test_github_routes_require_only_authentication():
    github_routes = [r for r in github_router.routes if isinstance(r, APIRoute)]
    assert github_routes, "github 라우트가 등록돼 있어야 한다"
    for route in github_routes:
        calls = _dependency_calls(route.dependant)
        names = {getattr(c, "__name__", "") for c in calls}
        assert "_require_developer" not in names, route.path
        assert get_current_user in calls, route.path


def test_access_token_has_no_account_type_claim():
    token = create_access_token("usr_1")
    payload = jwt.decode(token, get_settings().auth.secret_key, algorithms=["HS256"])
    assert "account_type" not in payload
    assert payload["sub"] == "usr_1"


def _entry() -> JournalEntry:
    return JournalEntry(
        id="ent_1",
        user_id="usr_1",
        date_key="2026-11-02",
        title="t",
        content="c",
        retro_type=RetroType.DAILY,
        created_at=datetime(2026, 11, 2, tzinfo=UTC),
    )


class _FakeGetEntry:
    async def execute(self, entry_id: str, user_id: str) -> JournalEntry:
        return _entry()


class _FakeOAuthRepo:
    def __init__(self, connections: list[OAuthConnection]) -> None:
        self._connections = connections

    async def find_by_user_id(self, user_id: str) -> list[OAuthConnection]:
        return self._connections


class _FakePushRepo:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def find_by_period(self, user_id, period_type, period_key):
        self.calls.append((user_id, period_type, period_key))
        return None


def _github_connection() -> OAuthConnection:
    return OAuthConnection(
        id="oauth_1",
        user_id="usr_1",
        provider=OAuthProvider.GITHUB,
        provider_user_id="42",
        access_token="gho_x",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


async def test_get_entry_attaches_push_info_when_github_connected():
    push_repo = _FakePushRepo()
    res = await get_entry(
        entry_id="ent_1",
        use_case=_FakeGetEntry(),
        push_repo=push_repo,
        oauth_repo=_FakeOAuthRepo([_github_connection()]),
        current_user=SimpleNamespace(id="usr_1"),
    )
    assert push_repo.calls, "GitHub 연결 사용자는 push 정보를 조회해야 한다"
    assert "github_push" in type(res.data).model_fields


async def test_get_entry_skips_push_info_without_github():
    push_repo = _FakePushRepo()
    res = await get_entry(
        entry_id="ent_1",
        use_case=_FakeGetEntry(),
        push_repo=push_repo,
        oauth_repo=_FakeOAuthRepo([]),
        current_user=SimpleNamespace(id="usr_1"),
    )
    assert push_repo.calls == []
    assert "github_push" not in type(res.data).model_fields
