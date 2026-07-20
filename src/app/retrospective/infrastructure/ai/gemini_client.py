"""Gemini SDK 래퍼 — 회고 요약 마크다운 생성.

설계:
- response_schema 없이 마크다운 직접 출력. 프롬프트가 사용자 템플릿 블록 구조를
  그대로 따르도록 지시하며, Gemini 2.5 Flash 는 이 지시를 신뢰도 높게 따른다.
- `response.text` 가 None 인 케이스(safety filter, blocked candidates 등) 명시적
  방어 → 식별 가능한 예외로 변환. 호출자가 retry/Failed 분기를 정확히 판단할 수
  있게 한다.
- 503 등 transient 에러는 SDK 의 ServerError 그대로 위로 전파 → Celery autoretry
  에서 처리.
"""
import structlog
from google import genai
from google.genai import types

from app.retrospective.domain.exceptions.exceptions import (
    SummaryInvalidStateException,
)
from app.retrospective.domain.models.value_objects import SummaryContent
from app.shared.infrastructure.config.ai import AIConfig

_log = structlog.get_logger(__name__)


class GeminiSummaryClient:
    def __init__(self, config: AIConfig) -> None:
        self._client = genai.Client(
            api_key=config.google_api_key,
            http_options=types.HttpOptions(timeout=config.gemini_timeout_ms),
        )
        self._model = config.gemini_model

    async def generate(self, prompt: str) -> SummaryContent:
        """마크다운 요약 생성.

        response_schema 없이 text/plain 으로 받는다. 프롬프트가 템플릿 블록
        구조를 지시하므로 Gemini 가 헤딩/불릿/체크박스 등을 그대로 재현한다.
        """
        config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )

        text = response.text
        if text is None:
            finish_reasons: list[str] = []
            for cand in (response.candidates or []):
                fr = getattr(cand, "finish_reason", None)
                if fr is not None:
                    finish_reasons.append(str(fr))
            _log.warning(
                "gemini.summary.empty_text",
                finish_reasons=finish_reasons,
                prompt_feedback=str(getattr(response, "prompt_feedback", None)),
            )
            raise SummaryInvalidStateException(
                "Gemini returned no text (safety filter or empty candidates)."
            )

        return SummaryContent.from_text(text)
