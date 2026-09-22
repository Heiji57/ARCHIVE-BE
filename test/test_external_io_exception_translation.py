"""외부 연동(AI·메일·GitHub·Calendar·Redis) 예외를 경계에서 도메인 예외로 번역하는지,
그리고 호출부가 실패 종류별로 다르게 대응하는지.

이전에는 라이브러리 예외(httpx·genai·aiosmtplib·redis)와 응답 형식 오류(KeyError)가 그대로
올라가 봉투 없는 500 이 되거나, 호출부의 `except Exception` 이 전부 같은 방식으로 삼켰다.
대표적인 오분류:
- Gemini 빈 응답 → topic 은 DigestNotFoundException(404 의미), 요약은 SummaryInvalidState
- GitHub 403(권한)·429 → 전부 GITHUB_API_UNAVAILABLE ("잠시 후 재시도" 안내)
- Calendar 토큰 갱신 5xx → CalendarReauthRequired → 장애 한 번에 사용자가 재연결해야 함
- Calendar 속도 제한 → push 재시도 횟수 소진 → push 영구 포기
"""
import json
from types import SimpleNamespace

import aiosmtplib
import httpx
import pytest
from google.genai import errors as genai_errors
from redis.exceptions import ConnectionError as RedisConnectionError

from app.github.domain.exceptions.exceptions import (
    GitHubApiUnavailableException,
    GitHubPermissionDeniedException,
    GitHubPushFailedException,
    GitHubRateLimitedException,
    GitHubResponseInvalidException,
    GitHubTokenInvalidException,
)
from app.github.infrastructure.api.github_api_client import GitHubApiClient
from app.google_calendar.domain.exceptions.exceptions import (
    CalendarApiUnavailableException,
    CalendarRateLimitedException,
    CalendarReauthRequiredException,
    CalendarResponseInvalidException,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (
    CalendarEventWrite,
    GoogleCalendarApiClient,
)
from app.shared.domain.exceptions.external import (
    AIEmptyResponseException,
    AIQuotaExceededException,
    AIRequestRejectedException,
    AIServiceUnavailableException,
    EmailDeliveryFailedException,
)
from app.shared.infrastructure.ai import errors as ai_errors

# ── AI 번역 ────────────────────────────────────────────────────────────────────


async def _raise(exc):
    raise exc


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (genai_errors.ServerError(code=503, response_json={}), AIServiceUnavailableException),
        (
            genai_errors.ClientError(
                code=429, response_json={"error": {"status": "RESOURCE_EXHAUSTED"}}
            ),
            AIQuotaExceededException,
        ),
        (
            genai_errors.ClientError(code=400, response_json={"error": {"status": "INVALID"}}),
            AIRequestRejectedException,
        ),
        (genai_errors.UnknownApiResponseError("garbage"), AIServiceUnavailableException),
        (httpx.ReadTimeout("slow"), AIServiceUnavailableException),
    ],
)
async def test_genai_errors_are_translated(raised, expected):
    with pytest.raises(expected) as ei:
        await ai_errors.call("op", _raise(raised))
    assert ei.value.__cause__ is raised


async def test_non_ai_errors_propagate_untouched():
    """번역 대상이 아닌 예외(코드 버그)를 AI 장애로 위장하면 안 된다."""
    with pytest.raises(KeyError):
        await ai_errors.call("op", _raise(KeyError("x")))


def test_quota_is_a_kind_of_unavailable_so_retry_paths_catch_it():
    assert issubclass(AIQuotaExceededException, AIServiceUnavailableException)


class _FakeModels:
    def __init__(self, response) -> None:
        self._response = response

    async def generate_content(self, **kw):
        return self._response

    async def embed_content(self, **kw):
        return self._response


def _with_fake_response(client, response):
    client._client = SimpleNamespace(aio=SimpleNamespace(models=_FakeModels(response)))
    return client


_AI_CFG = SimpleNamespace(google_api_key="k", gemini_timeout_ms=1000, gemini_model="m")


async def test_summary_empty_text_is_ai_empty_response():
    from app.retrospective.infrastructure.ai.gemini_client import GeminiSummaryClient

    client = _with_fake_response(
        GeminiSummaryClient(_AI_CFG), SimpleNamespace(text=None, candidates=[])
    )
    with pytest.raises(AIEmptyResponseException):
        await client.generate("p")


async def test_digest_empty_text_is_ai_empty_response_not_digest_not_found():
    from app.topic.infrastructure.ai.gemini_client import TopicGeminiClient

    client = _with_fake_response(TopicGeminiClient(_AI_CFG), SimpleNamespace(text=None))
    with pytest.raises(AIEmptyResponseException):
        await client.generate("p")


async def test_empty_embedding_is_ai_empty_response():
    from app.topic.infrastructure.ai.embedding_service import EmbeddingService

    client = _with_fake_response(EmbeddingService(_AI_CFG), SimpleNamespace(embeddings=[]))
    with pytest.raises(AIEmptyResponseException):
        await client.embed_text("t")
    with pytest.raises(AIEmptyResponseException):
        await client.embed_batch(["t"])


# ── SMTP ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raised",
    [aiosmtplib.SMTPServerDisconnected("bye"), ConnectionRefusedError("refused")],
)
async def test_smtp_failure_is_email_delivery_failed_without_full_address(monkeypatch, raised):
    from app.shared.infrastructure.email import smtp

    async def fake_send(*a, **kw):
        raise raised

    monkeypatch.setattr(smtp.aiosmtplib, "send", fake_send)
    with pytest.raises(EmailDeliveryFailedException) as ei:
        await smtp.send_email("secret.person@example.com", "s", "b")
    assert "example.com" in ei.value.message
    assert "secret.person" not in ei.value.message, "수신자 로컬파트(PII)가 예외 메시지에 남았다"


async def test_password_reset_background_send_swallows_delivery_failure(monkeypatch):
    """응답 이후 실행되는 BackgroundTasks — 여기서 새면 요청과 무관한 ASGI traceback 만 남는다."""
    from app.auth.presentation import router as auth_router

    async def failing_send(**kw):
        raise EmailDeliveryFailedException("smtp down")

    monkeypatch.setattr(auth_router, "send_email", failing_send)
    await auth_router._send_password_reset_email(to="a@b.com", subject="s", body="b")


# ── GitHub ─────────────────────────────────────────────────────────────────────


def _github(handler) -> GitHubApiClient:
    client = GitHubApiClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def _raise_connect(request):
    raise httpx.ConnectError("boom", request=request)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(401), GitHubTokenInvalidException),
        (
            httpx.Response(403, json={"message": "Resource not accessible"}),
            GitHubPermissionDeniedException,
        ),
        (httpx.Response(403, headers={"x-ratelimit-remaining": "0"}), GitHubRateLimitedException),
        (httpx.Response(403, headers={"retry-after": "60"}), GitHubRateLimitedException),
        (httpx.Response(429), GitHubRateLimitedException),
        (httpx.Response(502), GitHubApiUnavailableException),
        (httpx.Response(200, text="<html/>"), GitHubResponseInvalidException),
        (httpx.Response(200, json={"id": 1}), GitHubResponseInvalidException),
    ],
)
async def test_github_status_and_body_classification(response, expected):
    with pytest.raises(expected):
        await _github(lambda r: response).get_repository("tok", 1)


async def test_github_transport_error_is_unavailable():
    with pytest.raises(GitHubApiUnavailableException) as ei:
        await _github(_raise_connect).get_authenticated_user("tok")
    assert isinstance(ei.value.__cause__, httpx.TransportError)


def test_response_invalid_is_not_unavailable_so_it_stays_per_repo():
    """get_commits_by_date 는 Unavailable 을 요청 전체 실패로 본다 — 한 repo 의 응답 이상이
    전체를 죽이지 않으려면 ResponseInvalid 는 Unavailable 계열이면 안 된다."""
    assert not issubclass(GitHubResponseInvalidException, GitHubApiUnavailableException)


async def test_github_put_timeout_is_push_failed_not_retryable_unavailable():
    """쓰기 타임아웃은 이미 commit 됐을 수 있다 — 503(재시도 권장)이면 중복 commit 위험."""

    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GitHubPushFailedException):
        await _github(handler).put_file("tok", "o", "r", "a.md", b"x", "msg", "main")


# ── Google Calendar ────────────────────────────────────────────────────────────

_CAL_CFG = SimpleNamespace(
    client_id="id",
    client_secret="s",
    calendar_redirect_uri="http://cb",
    calendar_scope="scope",
)
_EVENT = CalendarEventWrite(
    archive_todo_id="todo_1",
    title="t",
    description=None,
    date_key="2026-09-22",
    start_at=None,
    end_at=None,
    timezone=None,
)


def _calendar(handler) -> GoogleCalendarApiClient:
    client = GoogleCalendarApiClient(_CAL_CFG)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(429), CalendarRateLimitedException),
        (
            httpx.Response(403, json={"error": {"errors": [{"reason": "rateLimitExceeded"}]}}),
            CalendarRateLimitedException,
        ),
        (httpx.Response(200, json={"kind": "event"}), CalendarResponseInvalidException),
        (httpx.Response(200, text="oops"), CalendarResponseInvalidException),
        (httpx.Response(500), CalendarApiUnavailableException),
        (httpx.Response(401), CalendarReauthRequiredException),
    ],
)
async def test_calendar_create_classification(response, expected):
    with pytest.raises(expected):
        await _calendar(lambda r: response).create_event("tok", _EVENT)


def test_calendar_new_exceptions_keep_existing_unavailable_handling():
    assert issubclass(CalendarRateLimitedException, CalendarApiUnavailableException)
    assert issubclass(CalendarResponseInvalidException, CalendarApiUnavailableException)


async def test_calendar_transport_error_is_unavailable():
    with pytest.raises(CalendarApiUnavailableException):
        await _calendar(_raise_connect).create_event("tok", _EVENT)


async def test_calendar_token_refresh_5xx_is_not_reauth():
    """Google 일시 장애로 refresh 가 5xx 를 주면 refresh_token 은 멀쩡하다."""
    with pytest.raises(CalendarApiUnavailableException) as ei:
        await _calendar(lambda r: httpx.Response(503)).refresh_access_token("rt")
    assert not isinstance(ei.value, CalendarReauthRequiredException)


async def test_calendar_token_refresh_invalid_grant_is_reauth():
    handler = lambda r: httpx.Response(400, json={"error": "invalid_grant"})  # noqa: E731
    with pytest.raises(CalendarReauthRequiredException):
        await _calendar(handler).refresh_access_token("rt")


async def test_calendar_token_response_missing_access_token_is_response_invalid():
    handler = lambda r: httpx.Response(200, json={"expires_in": 3600})  # noqa: E731
    with pytest.raises(CalendarResponseInvalidException):
        await _calendar(handler).refresh_access_token("rt")


# ── Calendar push 워커: 속도 제한은 재시도 횟수를 소진시키지 않는다 ─────────────


async def test_push_rate_limited_does_not_consume_retry_budget(monkeypatch):
    import app.worker.tasks.push_calendars as push

    recorded: dict = {}

    class _Begin:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):
            return False

    class _Factory:
        def begin(self):
            return _Begin()

    class _Repo:
        def __init__(self, session) -> None:
            pass

        async def heartbeat_push(self, todo_id, user_id, attempt_id):
            return True

        async def finalize_push_failure(self, todo_id, user_id, attempt_id, retry_count):
            recorded["retry_count"] = retry_count
            return True

    class _RateLimitedService:
        def __init__(self, api_client) -> None:
            pass

        async def push_one(self, access_token, todo):
            raise CalendarRateLimitedException("429")

    class _Redis:
        async def publish(self, channel, message):
            pass

    monkeypatch.setattr(push, "TodoRepository", _Repo)
    monkeypatch.setattr(push, "CalendarPushService", _RateLimitedService)
    todo = SimpleNamespace(id="todo_1", sync_attempt_id="att", push_retry_count=2)

    await push._process_claimed(_Factory(), None, _Redis(), "usr_1", [todo], "tok")
    assert recorded["retry_count"] == 2, (
        "속도 제한으로 retry_count 가 올라가면 push 를 영구 포기한다"
    )


async def test_delete_event_task_retries_on_unavailable(monkeypatch):
    """예전 `autoretry_for` 는 celery_aio_pool 의 async task 에서 작동하지 않았다."""
    import app.worker.tasks.push_calendars as push

    retried: list = []

    async def token(*a, **kw):
        return "tok"

    class _Client:
        def __init__(self, cfg) -> None:
            pass

        async def delete_event(self, token, gid):
            raise CalendarApiUnavailableException("503")

        async def close(self):
            pass

    class _RetryScheduledError(Exception):
        pass

    def fake_retry(*, exc=None, countdown=None, **kw):
        retried.append(exc)
        raise _RetryScheduledError

    monkeypatch.setattr(push, "_acquire_access_token", token)
    monkeypatch.setattr(push, "GoogleCalendarApiClient", _Client)
    monkeypatch.setattr(push, "get_worker_session_factory", lambda: None)
    monkeypatch.setattr(push.delete_calendar_event_task, "retry", fake_retry)

    with pytest.raises(_RetryScheduledError):
        await push.delete_calendar_event_task.run("usr_1", "gid_1")
    assert len(retried) == 1 and isinstance(retried[0], CalendarApiUnavailableException)


# ── GitHub 연결 상태: 코드 버그를 "연결 끊김" 으로 위장하지 않는다 ─────────────


def _connection_use_case(api_client):
    from app.github.application.use_cases.get_connection_status import GetConnectionStatusUseCase

    class _Settings:
        async def find_by_user_id(self, user_id):
            return SimpleNamespace(github_push_target_repository_id=None)

    from app.auth.domain.models.value_objects import OAuthProvider

    class _OAuth:
        async def find_by_user_id(self, user_id):
            return [
                SimpleNamespace(
                    provider=OAuthProvider.GITHUB,
                    access_token="tok",
                    provider_verified_emails=["a@b.com"],
                )
            ]

    return GetConnectionStatusUseCase(_OAuth(), _Settings(), api_client)


async def test_connection_status_token_invalid_is_disconnected():
    class _Api:
        async def get_authenticated_user(self, token):
            raise GitHubTokenInvalidException()

    status = await _connection_use_case(_Api()).execute("usr_1")
    assert status.connected is False


async def test_connection_status_code_bug_propagates():
    class _Api:
        async def get_authenticated_user(self, token):
            raise KeyError("login")

    with pytest.raises(KeyError):
        await _connection_use_case(_Api()).execute("usr_1")


# ── Redis 장애: fail-closed 503 (v1 은 기존 500 INTERNAL_ERROR) ─────────────────


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/api/v2/auth/email/verify/send", 503, "CACHE_UNAVAILABLE"),
        ("/api/v1/auth/login", 500, "INTERNAL_ERROR"),
    ],
)
async def test_redis_error_is_cache_unavailable(path, status, code):
    from redis.exceptions import RedisError

    from app.main import app

    handler = app.exception_handlers[RedisError]
    request = SimpleNamespace(url=SimpleNamespace(path=path))
    response = await handler(request, RedisConnectionError("down"))
    assert response.status_code == status
    assert json.loads(response.body)["code"] == code


@pytest.mark.parametrize(
    ("exc", "v1_code", "v1_status"),
    [
        (CalendarRateLimitedException(), "GOOGLE_CALENDAR_API_UNAVAILABLE", 503),
        (CalendarResponseInvalidException(), "GOOGLE_CALENDAR_API_UNAVAILABLE", 503),
        (GitHubPermissionDeniedException(), "GITHUB_API_UNAVAILABLE", 503),
        (GitHubResponseInvalidException(), "INTERNAL_ERROR", 500),
        (EmailDeliveryFailedException(), "INTERNAL_ERROR", 500),
    ],
)
def test_new_io_codes_keep_v1_contract(exc, v1_code, v1_status):
    """v2 가 없는 엔드포인트(GitHub·Calendar 등)는 새 코드를 v1 에서 기존 코드로 보낸다."""
    from app.shared.infrastructure.errors.handler import to_http_response

    response = to_http_response(exc, api_version="v1")
    assert (response.status_code, json.loads(response.body)["code"]) == (v1_status, v1_code)


async def test_github_list_branches_and_commits_parse_through_translation():
    """_parse 로 옮기면서 페이지 종료 조건이 옛 변수명(items)을 참조해 NameError 가 나던 회귀."""
    commit = {
        "sha": "abc",
        "html_url": "https://github.com/o/r/commit/abc",
        "commit": {"message": "m", "author": {"date": "2026-09-22T00:00:00Z"}},
    }

    def handler(request):
        if request.url.path.endswith("/branches"):
            return httpx.Response(200, json=[{"name": "main"}])
        return httpx.Response(200, json=[commit])

    client = _github(handler)
    assert await client.list_branches("tok", "o", "r") == ["main"]
    commits = await client.list_commits("tok", "o", "r", "2026-09-22T00:00:00Z", "2026-09-23")
    assert [c.sha for c in commits] == ["abc"]


async def test_github_malformed_commit_is_response_invalid():
    handler = lambda r: httpx.Response(200, json=[{"sha": "abc"}])  # noqa: E731
    with pytest.raises(GitHubResponseInvalidException):
        await _github(handler).list_commits("tok", "o", "r", "a", "b")
