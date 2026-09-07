"""Gemini 마크다운 생성 래퍼 — 토픽 다이제스트 전용."""
import structlog
from google import genai
from google.genai import types

from app.shared.infrastructure.config.ai import AIConfig
from app.topic.domain.exceptions.exceptions import DigestNotFoundException

_log = structlog.get_logger(__name__)


class TopicGeminiClient:
    def __init__(self, config: AIConfig) -> None:
        self._client = genai.Client(
            api_key=config.google_api_key,
            http_options=types.HttpOptions(timeout=config.gemini_timeout_ms),
        )
        self._model = config.gemini_model

    async def generate(self, prompt: str) -> str:
        """마크다운 다이제스트 생성. 반환값은 마크다운 문자열."""
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
            # safety filter / blocked — cannot generate digest
            raise DigestNotFoundException(
                "Gemini blocked the response (safety filter or empty candidates)."
            )
        return text.strip()
