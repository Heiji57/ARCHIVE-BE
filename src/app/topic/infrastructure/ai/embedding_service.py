"""Gemini gemini-embedding-001 래퍼 — 토픽 다이제스트 임베딩 생성."""
import structlog
from google import genai
from google.genai import types

from app.shared.infrastructure.config.ai import AIConfig

_log = structlog.get_logger(__name__)

_EMBEDDING_MODEL = "models/gemini-embedding-001"
_EMBEDDING_DIM = 768
_EMBED_CONFIG = types.EmbedContentConfig(output_dimensionality=_EMBEDDING_DIM)


class EmbeddingService:
    def __init__(self, config: AIConfig) -> None:
        self._client = genai.Client(
            api_key=config.google_api_key,
            http_options=types.HttpOptions(timeout=config.gemini_timeout_ms),
        )

    async def embed_text(self, text: str) -> list[float]:
        response = await self._client.aio.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=text,
            config=_EMBED_CONFIG,
        )
        return list(response.embeddings[0].values)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """여러 텍스트를 한 번에 임베딩. API 호출 1회."""
        if not texts:
            return []
        response = await self._client.aio.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=texts,
            config=_EMBED_CONFIG,
        )
        return [list(e.values) for e in response.embeddings]
