"""Gemini 호출 토큰 사용량 로깅 — 비용 실측용 `ai.usage` 이벤트.

비용(달러)은 기록하지 않는다 — 단가가 바뀌면 코드 속 가격표가 조용히 틀린다. 토큰만
남기고 비용은 조회 시점 단가로 계산한다(`develop.md` 의 jq 예시). user_id·task_name 은
structlog contextvars 로 자동으로 붙는다(요청 경로는 인증 미들웨어, 워커는 태스크가 바인드).
"""
from typing import Any

import structlog

_log = structlog.get_logger("ai.usage")


def log_generate_usage(operation: str, model: str, response: Any) -> None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        _log.warning("ai.usage.missing", operation=operation, model=model)
        return
    _log.info(
        "ai.usage",
        operation=operation,
        model=model,
        input_tokens=usage.prompt_token_count or 0,
        output_tokens=usage.candidates_token_count or 0,
        thinking_tokens=usage.thoughts_token_count or 0,
        cached_tokens=usage.cached_content_token_count or 0,
    )


def log_embed_usage(operation: str, model: str, texts: list[str]) -> None:
    """Gemini API 의 임베딩 응답엔 토큰 수가 없다 — 입력 개수·글자 수로 대신 남긴다."""
    _log.info(
        "ai.usage",
        operation=operation,
        model=model,
        input_count=len(texts),
        input_chars=sum(len(t) for t in texts),
    )
