"""`generate_summary_task` 가 Gemini 5xx/타임아웃을 만나면 `autoretry_for` 가 아니라
`self.retry()` 를 직접 호출해 지수 백오프로 재시도하는지, 그리고 재시도가
소진됐을 때도 FAILED 마킹을 놓치지 않는지.

`autoretry_for` 데코레이터는 이 프로젝트의 실제 워커 풀 `celery_aio_pool.AsyncIOPool`
에서 `async def` task 에 대해 실제로 작동하지 않는다 — 자세한 이유는
`SummaryRowNotYetVisibleError` 의 docstring, 그리고
`test_generate_summary_retries_on_not_yet_visible_row.py` 참고. 원래 Gemini 재시도는
그 (작동하지 않는) `autoretry_for` 에 의존하고 있었다 — CLAUDE.md 에 문서화된 "Gemini
5xx 는 자동 재시도" 정책이 실제로는 지켜지지 않고 있었다는 뜻.

처음엔 `except (genai_errors.ServerError, httpx.TimeoutException) as exc:` 를 바깥
try 의 **형제** except 절로 뒀는데, `Task.retry()` 는 `max_retries` 소진 시 `Retry`
가 아니라 우리가 넘긴 `exc`(원본 예외)를 그대로 재발생시킨다 — 그런데 그 재발생이
"어느 except 블록 안"에서 일어나면 Python 은 같은 try 문의 다른 형제 except 절로
다시 매칭해주지 않는다(직접 재현해 확인). 그래서 소진된 예외가 `except Retry:` /
`except Exception:` 을 모두 비껴가 FAILED 마킹·알림 없이 그대로 태스크가 죽고,
summary 는 IN_PROGRESS 에 영구히 멈췄다. 수정: Gemini 호출을 바깥 try **본문** 안에
중첩된 try/except 로 감싸, 소진된 예외가 중첩 try/except 를 완전히 빠져나온 뒤
바깥 try 의 except 절들로부터 새로 매칭되게 한다.
"""
from datetime import UTC, date, datetime

from google.genai import errors as genai_errors

import app.worker.tasks.generate_summary as generate_summary_module
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType

_NOW = datetime.now(UTC)


def _pending_summary() -> RetroSummary:
    return RetroSummary(
        id="summ_1",
        user_id="usr_1",
        summary_type=SummaryType.WEEKLY,
        period_start=date(2026, 8, 24),
        period_end=date(2026, 8, 30),
        status=SummaryStatus.PENDING,
        content=None,
        created_at=_NOW,
    )


class _FakeSummaryRepo:
    def __init__(self, summary: RetroSummary) -> None:
        self._summary = summary

    async def find_by_id(self, summary_id: str, user_id: str) -> RetroSummary:
        return self._summary

    async def save(self, summary: RetroSummary) -> RetroSummary:
        return summary


class _FakeUserSettingsRepo:
    async def find_by_user_id(self, user_id: str):
        return None


class _FakeStrategy:
    async def build_prompt(self, session, summary, user_template, locale) -> str:
        return "prompt"


class _FakeSessionCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeFactory:
    def begin(self) -> _FakeSessionCtx:
        return _FakeSessionCtx()


class _FakeRedis:
    async def publish(self, channel: str, message: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


class _FakeNotificationRepo:
    def __init__(self, session) -> None:
        pass

    async def save(self, notification):
        return notification


class _RaisingGeminiClient:
    """생성자에서 바로 Gemini 5xx 를 일으켜, `.generate()` 까지 갈 필요 없이
    `except (genai_errors.ServerError, ...)` 경로를 가장 간단하게 재현한다."""

    def __init__(self, ai_settings) -> None:
        raise genai_errors.ServerError(code=503, response_json={})


async def test_gemini_server_error_calls_self_retry_with_backoff_countdown(
    monkeypatch,
) -> None:
    summary = _pending_summary()
    calls: list[dict] = []

    def fake_retry(*, exc=None, countdown=None, **kwargs):
        calls.append({"exc": exc, "countdown": countdown})
        raise generate_summary_module.Retry(exc=exc)

    def fake_backoff(*, factor, retries, maximum, full_jitter):
        assert factor == generate_summary_module._GEMINI_RETRY_BACKOFF_FACTOR
        assert maximum == generate_summary_module._GEMINI_RETRY_BACKOFF_MAX_SECONDS
        assert full_jitter is True
        return 7  # 결정적인 값으로 고정해 검증을 단순화

    monkeypatch.setattr(
        generate_summary_module, "get_worker_session_factory", lambda: _FakeFactory()
    )
    monkeypatch.setattr(
        generate_summary_module,
        "RetroSummaryRepository",
        lambda session: _FakeSummaryRepo(summary),
    )
    monkeypatch.setattr(
        generate_summary_module,
        "UserSettingsRepository",
        lambda session: _FakeUserSettingsRepo(),
    )
    monkeypatch.setattr(generate_summary_module, "get_strategy", lambda t: _FakeStrategy())
    monkeypatch.setattr(generate_summary_module, "GeminiSummaryClient", _RaisingGeminiClient)
    monkeypatch.setattr(
        generate_summary_module, "get_exponential_backoff_interval", fake_backoff
    )
    monkeypatch.setattr(
        generate_summary_module.Redis, "from_url", lambda *a, **kw: _FakeRedis()
    )
    monkeypatch.setattr(generate_summary_module.generate_summary_task, "retry", fake_retry)

    raised_type: type[BaseException] | None = None
    try:
        await generate_summary_module.generate_summary_task.run("summ_1", "usr_1")
    except Exception as exc:
        raised_type = type(exc)

    assert raised_type is generate_summary_module.Retry
    assert len(calls) == 1
    assert isinstance(calls[0]["exc"], genai_errors.ServerError)
    assert calls[0]["countdown"] == 7


async def test_gemini_error_exhausted_retries_still_marks_summary_failed(
    monkeypatch,
) -> None:
    summary = _pending_summary()
    published: list[tuple[str, str]] = []

    class _TrackingRedis(_FakeRedis):
        async def publish(self, channel: str, message: str) -> None:
            published.append((channel, message))

    def fake_retry_exhausted(*, exc=None, countdown=None, **kwargs):
        # 실제 Task.retry() 가 max_retries 소진 시 하는 것과 동일하게, Retry 가
        # 아니라 원본 exc 를 그대로 재발생시킨다 (celery/app/task.py Task.retry).
        raise exc

    monkeypatch.setattr(
        generate_summary_module, "get_worker_session_factory", lambda: _FakeFactory()
    )
    monkeypatch.setattr(
        generate_summary_module,
        "RetroSummaryRepository",
        lambda session: _FakeSummaryRepo(summary),
    )
    monkeypatch.setattr(
        generate_summary_module,
        "UserSettingsRepository",
        lambda session: _FakeUserSettingsRepo(),
    )
    monkeypatch.setattr(generate_summary_module, "get_strategy", lambda t: _FakeStrategy())
    monkeypatch.setattr(generate_summary_module, "GeminiSummaryClient", _RaisingGeminiClient)
    monkeypatch.setattr(
        generate_summary_module, "get_exponential_backoff_interval", lambda **kw: 7
    )
    monkeypatch.setattr(
        generate_summary_module,
        "NotificationRepository",
        lambda session: _FakeNotificationRepo(session),
    )
    monkeypatch.setattr(
        generate_summary_module.Redis, "from_url", lambda *a, **kw: _TrackingRedis()
    )
    monkeypatch.setattr(
        generate_summary_module.generate_summary_task, "retry", fake_retry_exhausted
    )

    raised_type: type[BaseException] | None = None
    try:
        await generate_summary_module.generate_summary_task.run("summ_1", "usr_1")
    except Exception as exc:
        raised_type = type(exc)

    assert raised_type is genai_errors.ServerError, (
        "소진 시 self.retry() 는 Retry 가 아니라 원본 exc 를 그대로 재발생시킨다"
    )
    assert summary.status == SummaryStatus.FAILED, (
        "재시도 소진 후 FAILED 마킹 없이 IN_PROGRESS 로 영구히 남으면 안 된다 (회귀 재현)"
    )
    assert any(
        ch == f"summary:{summary.id}" and "failed" in msg for ch, msg in published
    ), "요약 상태 채널에 failed publish 가 나가야 SSE 구독자가 무한 대기하지 않는다"
    assert any(ch == "notifications:usr_1" for ch, _ in published), (
        "재시도 소진은 진짜 실패이므로 사용자에게 실패 알림이 가야 한다"
    )
