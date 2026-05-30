import json
import re

from google import genai
from google.genai import types

from app.retrospective.domain.models.value_objects import SummaryContent
from app.shared.infrastructure.config.ai import AIConfig


class GeminiSummaryClient:
    def __init__(self, config: AIConfig) -> None:
        self._client = genai.Client(api_key=config.google_api_key)
        self._model = config.gemini_model

    async def generate(self, prompt: str) -> SummaryContent:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return self._parse(response.text)

    def _parse(self, text: str) -> SummaryContent:
        # response_mime_type=application/json 이면 순수 JSON이 오지만,
        # 방어적으로 마크다운 코드블록도 처리
        match = re.search(r"\{.*\}", text, re.DOTALL)
        raw = match.group() if match else text
        data = json.loads(raw)
        return SummaryContent(
            achievements=tuple(data.get("achievements", [])),
            challenges=tuple(data.get("challenges", [])),
            learnings=tuple(data.get("learnings", [])),
            next_focus=tuple(data.get("next_focus", [])),
        )
