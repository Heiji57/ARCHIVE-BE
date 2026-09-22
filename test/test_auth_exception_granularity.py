"""auth 보안 경로의 예외 세분화 + v1 하위호환.

이전에는 서로 다른 실패가 한 코드로 뭉개졌다:
- 이메일 인증 코드 틀림/만료/시도 초과/재발송 쿨다운 → 전부 401 AUTH_TOKEN_INVALID
- OAuth provider 장애·응답 형식 오류 → KeyError 로 500
- OAuth code 재사용·미인증 이메일 → AUTH_OAUTH_STATE_INVALID (state 위조와 구분 불가)
- JWT 에 sub 가 없으면 KeyError 로 500

v2 엔드포인트는 세분화된 코드를 그대로 내보내고, v1 은 기존 코드로 되돌려 매핑한다.
OAuth callback 은 provider 에 등록된 redirect_uri 라 v1 경로에 고정 — 흐름을 시작한
authorize/link-init 의 버전을 state 에 기록해 callback 이 그 버전의 코드를 쓴다.
"""
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from jose import jwt

from app.auth.domain.exceptions.exceptions import (
    AuthTokenInvalidException,
    EmailCodeAttemptsExceededException,
    EmailCodeExpiredException,
    EmailCodeInvalidException,
    EmailSendCooldownException,
    OAuthCodeInvalidException,
    OAuthEmailNotVerifiedException,
    OAuthProviderResponseInvalidException,
    OAuthProviderUnavailableException,
)
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.oauth.github_client import GitHubOAuthClient
from app.auth.infrastructure.oauth.google_client import GoogleOAuthClient
from app.auth.presentation.router import oauth_callback
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.errors.handler import to_http_response


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)

    async def exists(self, key):
        return int(key in self.store)

    async def getdel(self, key):
        return self.store.pop(key, None)


def _auth_config(**overrides):
    base = dict(
        email_verify_code_ttl_seconds=600,
        email_verified_ttl_seconds=1800,
        email_cooldown_ttl_seconds=60,
        email_max_verify_attempts=2,
        oauth_state_ttl_seconds=600,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ── 이메일 인증 ────────────────────────────────────────────────────────────────

async def test_verify_code_missing_is_expired():
    cache = EmailVerificationCache(_FakeRedis(), _auth_config())
    with pytest.raises(EmailCodeExpiredException):
        await cache.verify_code("a@b.com", "ABCDEF")


async def test_verify_code_wrong_then_attempts_exceeded():
    cache = EmailVerificationCache(_FakeRedis(), _auth_config(email_max_verify_attempts=2))
    await cache.create_code("a@b.com")
    for _ in range(2):
        with pytest.raises(EmailCodeInvalidException):
            await cache.verify_code("a@b.com", "WRONG1")
    with pytest.raises(EmailCodeAttemptsExceededException):
        await cache.verify_code("a@b.com", "WRONG1")


async def test_send_verification_on_cooldown_raises_cooldown():
    from app.auth.application.dtos.commands import SendEmailVerificationCommand
    from app.auth.application.use_cases.send_email_verification import (
        SendEmailVerificationUseCase,
    )

    redis = _FakeRedis()
    cache = EmailVerificationCache(redis, _auth_config())
    await cache.create_code("a@b.com")  # 쿨다운 키도 함께 세팅된다
    with pytest.raises(EmailSendCooldownException):
        await SendEmailVerificationUseCase(cache).execute(
            SendEmailVerificationCommand(email="a@b.com")
        )


# ── v1 legacy 매핑 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("exc", "v2_status", "v1_code", "v1_status"),
    [
        (EmailCodeInvalidException(), 400, "AUTH_TOKEN_INVALID", 401),
        (EmailCodeExpiredException(), 400, "AUTH_TOKEN_INVALID", 401),
        (EmailCodeAttemptsExceededException(), 429, "AUTH_TOKEN_INVALID", 401),
        (EmailSendCooldownException(), 429, "AUTH_TOKEN_INVALID", 401),
        (OAuthCodeInvalidException(), 400, "AUTH_OAUTH_STATE_INVALID", 400),
        (OAuthEmailNotVerifiedException(), 400, "AUTH_OAUTH_STATE_INVALID", 400),
        (OAuthProviderUnavailableException(), 503, "INTERNAL_ERROR", 500),
        (OAuthProviderResponseInvalidException(), 502, "INTERNAL_ERROR", 500),
    ],
)
def test_v2_exposes_new_code_and_v1_keeps_legacy(exc, v2_status, v1_code, v1_status):
    v2 = to_http_response(exc, api_version="v2")
    assert v2.status_code == v2_status
    assert json.loads(v2.body)["code"] == exc.code

    v1 = to_http_response(exc, api_version="v1")
    assert v1.status_code == v1_status
    assert json.loads(v1.body)["code"] == v1_code


# ── OAuth 클라이언트: 외부 응답 → 도메인 예외 번역 ─────────────────────────────

_OAUTH_CFG = SimpleNamespace(client_id="id", client_secret="secret", redirect_uri="http://cb")


def _google(handler) -> GoogleOAuthClient:
    return GoogleOAuthClient(_OAUTH_CFG, transport=httpx.MockTransport(handler))


def _github(handler) -> GitHubOAuthClient:
    return GitHubOAuthClient(_OAUTH_CFG, transport=httpx.MockTransport(handler))


def _raise_connect(request):
    raise httpx.ConnectError("boom", request=request)


def _raise_timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize("factory", [_google, _github])
@pytest.mark.parametrize("handler", [_raise_connect, _raise_timeout])
async def test_oauth_transport_error_is_provider_unavailable(factory, handler):
    with pytest.raises(OAuthProviderUnavailableException) as ei:
        await factory(handler).exchange_code("code")
    assert isinstance(ei.value.__cause__, httpx.TransportError)


@pytest.mark.parametrize("factory", [_google, _github])
async def test_oauth_provider_5xx_is_unavailable(factory):
    with pytest.raises(OAuthProviderUnavailableException):
        await factory(lambda r: httpx.Response(502, text="bad gateway")).exchange_code("c")


@pytest.mark.parametrize(
    ("factory", "status", "error"),
    [(_google, 400, "invalid_grant"), (_github, 200, "bad_verification_code")],
)
async def test_oauth_code_rejected_is_code_invalid(factory, status, error):
    handler = lambda r: httpx.Response(status, json={"error": error})  # noqa: E731
    with pytest.raises(OAuthCodeInvalidException):
        await factory(handler).exchange_code("reused")


@pytest.mark.parametrize("factory", [_google, _github])
async def test_oauth_client_misconfig_is_response_invalid(factory):
    handler = lambda r: httpx.Response(401, json={"error": "invalid_client"})  # noqa: E731
    with pytest.raises(OAuthProviderResponseInvalidException):
        await factory(handler).exchange_code("c")


@pytest.mark.parametrize("factory", [_google, _github])
@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, text="<html>not json</html>"), httpx.Response(200, json={"foo": 1})],
)
async def test_oauth_malformed_token_response_is_response_invalid(factory, response):
    with pytest.raises(OAuthProviderResponseInvalidException):
        await factory(lambda r: response).exchange_code("c")


async def test_google_unverified_email():
    handler = lambda r: httpx.Response(  # noqa: E731
        200, json={"id": "1", "email": "a@b.com", "verified_email": False}
    )
    with pytest.raises(OAuthEmailNotVerifiedException):
        await _google(handler).get_user_info("tok")


async def test_google_userinfo_missing_id_is_response_invalid():
    handler = lambda r: httpx.Response(  # noqa: E731
        200, json={"email": "a@b.com", "verified_email": True}
    )
    with pytest.raises(OAuthProviderResponseInvalidException):
        await _google(handler).get_user_info("tok")


async def test_github_no_verified_primary_email():
    def handler(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 1, "login": "me"})
        return httpx.Response(
            200, json=[{"email": "a@b.com", "primary": True, "verified": False}]
        )

    with pytest.raises(OAuthEmailNotVerifiedException):
        await _github(handler).get_user_info("tok")


async def test_github_user_info_success():
    def handler(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 7, "login": "me"})
        return httpx.Response(
            200, json=[{"email": "a@b.com", "primary": True, "verified": True}]
        )

    info = await _github(handler).get_user_info("tok")
    assert (info.provider_user_id, info.email, info.login) == ("7", "a@b.com", "me")


# ── JWT ────────────────────────────────────────────────────────────────────────

async def test_access_token_without_sub_is_invalid_not_500():
    token = jwt.encode(
        {"type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        get_settings().auth.secret_key,
        algorithm="HS256",
    )
    with pytest.raises(AuthTokenInvalidException):
        await get_current_user(SimpleNamespace(credentials=token))


# ── OAuth state 버전 기록 + callback 버전별 코드 ────────────────────────────────

async def test_state_records_api_version():
    cache = OAuthStateCache(_FakeRedis(), _auth_config())
    v2_state = await cache.create_state("github", api_version="v2")
    v1_state = await cache.create_state("github")
    link_state = await cache.create_link_state("google", "user_1", api_version="v2")

    assert await cache.peek_api_version(v2_state) == "v2"
    assert await cache.peek_api_version(v1_state) == "v1"
    assert await cache.peek_api_version(link_state) == "v2"
    assert await cache.peek_api_version("unknown") == "v1"
    # peek 는 1회용 state 를 소비하지 않는다
    assert (await cache.consume_state(v2_state))["provider"] == "github"


class _RaisingUseCase:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(self, **kwargs):
        raise self._exc


def _posted_error(html_response) -> str:
    body = html_response.body.decode()
    start = body.index("postMessage(") + len("postMessage(")
    payload, _ = json.JSONDecoder().raw_decode(body[start:])
    return payload["error"]


@pytest.mark.parametrize(
    ("version", "expected"),
    [("v2", "AUTH_OAUTH_PROVIDER_UNAVAILABLE"), ("v1", "INTERNAL_ERROR")],
)
async def test_callback_error_code_follows_state_version(version, expected):
    cache = OAuthStateCache(_FakeRedis(), _auth_config())
    state = await cache.create_state("github", api_version=version)
    resp = await oauth_callback(
        provider=OAuthProvider.GITHUB,
        request=SimpleNamespace(headers={}, client=None),
        use_case=_RaisingUseCase(OAuthProviderUnavailableException()),
        state_cache=cache,
        code="c",
        state=state,
        error=None,
    )
    assert _posted_error(resp) == expected
