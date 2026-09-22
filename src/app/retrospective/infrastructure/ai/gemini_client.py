"""Gemini SDK 래퍼 — 회고 요약 마크다운 생성.

설계:
- response_schema 없이 마크다운 직접 출력. 프롬프트가 사용자 템플릿 블록 구조를
  그대로 따르도록 지시하며, Gemini 2.5 Flash 는 이 지시를 신뢰도 높게 따른다.
- `response.text` 가 None 인 케이스(safety filter, blocked candidates 등) 명시적
  방어 → AIEmptyResponseException. 호출자가 retry/Failed 분기를 정확히 판단할 수
  있게 한다.
- SDK/httpx 예외는 shared AI 예외로 번역(`shared/infrastructure/ai/errors.py`) —
  일시 장애(Unavailable/QuotaExceeded)만 워커가 self.retry() 로 재시도한다.
"""
import structlog
from google import genai
from google.genai import types

from app.retrospective.domain.models.value_objects import SummaryContent
from app.shared.domain.exceptions.external import AIEmptyResponseException
from app.shared.infrastructure.ai import errors as ai_errors
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

        response = await ai_errors.call(
            "gemini.summary.generate",
            self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            ),
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
            raise AIEmptyResponseException(
                f"Gemini returned no text (finish_reasons={finish_reasons})."
            )

        return SummaryContent.from_text(text)
