"""Gemini 생성 래퍼 — 토픽 다이제스트 전용."""

import json
from typing import Any

import structlog
from google import genai
from google.genai import types

from app.shared.domain.exceptions.external import AIEmptyResponseException
from app.shared.infrastructure.ai import errors as ai_errors
from app.shared.infrastructure.ai.usage import log_generate_usage
from app.shared.infrastructure.config.ai import AIConfig

_log = structlog.get_logger(__name__)


class TopicGeminiClient:
    def __init__(self, config: AIConfig) -> None:
        self._client = genai.Client(
            api_key=config.google_api_key,
            http_options=types.HttpOptions(timeout=config.gemini_timeout_ms),
        )
        self._model = config.gemini_model

    async def generate_json(self, prompt: str, schema: dict[str, Any]) -> Any:
        """JSON 응답 생성(`response_json_schema` 로 모양 강제). 파싱 실패는 ValueError.

        스키마가 있어도 모델이 잘리거나 깨진 JSON 을 줄 수 있어 호출자가 재요청을 판단한다.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        response = await ai_errors.call(
            "gemini.digest.generate",
            self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            ),
        )
        log_generate_usage("gemini.digest.generate", self._model, response)
        text = response.text
        if text is None:
            raise AIEmptyResponseException(
                "Gemini blocked the response (safety filter or empty candidates)."
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini returned invalid JSON: {e}") from e
