"""Gemini 호출마다 `ai.usage` 로그가 토큰 수를 남기는지 — 비용 실측의 유일한 데이터 소스."""
from types import SimpleNamespace

import structlog
from structlog.testing import capture_logs

from app.shared.infrastructure.ai.usage import log_embed_usage, log_generate_usage


def test_generate_usage_logs_token_counts() -> None:
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=2251,
            candidates_token_count=491,
            thoughts_token_count=None,
            cached_content_token_count=None,
        )
    )
    with capture_logs() as logs:
        log_generate_usage("gemini.summary.generate", "gemini-2.5-flash", response)

    assert logs == [
        {
            "event": "ai.usage",
            "log_level": "info",
            "operation": "gemini.summary.generate",
            "model": "gemini-2.5-flash",
            "input_tokens": 2251,
            "output_tokens": 491,
            "thinking_tokens": 0,
            "cached_tokens": 0,
        }
    ]


def test_generate_usage_missing_metadata_warns_instead_of_crashing() -> None:
    with capture_logs() as logs:
        log_generate_usage("gemini.digest.generate", "m", SimpleNamespace(usage_metadata=None))
    assert logs[0]["event"] == "ai.usage.missing"
    assert logs[0]["log_level"] == "warning"


def test_embed_usage_logs_count_and_chars() -> None:
    with capture_logs() as logs:
        log_embed_usage("gemini.embed_batch", "models/gemini-embedding-001", ["가나다", "abcd"])
    assert logs[0]["input_count"] == 2
    assert logs[0]["input_chars"] == 7


def test_bound_user_id_is_attached() -> None:
    """워커가 바인드한 user_id 가 붙어야 사용자별 원가를 집계할 수 있다."""
    structlog.contextvars.clear_contextvars()
    with structlog.contextvars.bound_contextvars(user_id="usr_1"):
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
            log_embed_usage("gemini.embed_text", "m", ["x"])
    assert logs[0]["user_id"] == "usr_1"
