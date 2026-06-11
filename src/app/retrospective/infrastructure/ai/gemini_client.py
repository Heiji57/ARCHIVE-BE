"""Gemini SDK 래퍼 — 회고 요약 JSON 생성.

설계:
- `response_schema` 로 출력 JSON 형태 강제 → "Korean keys" 같은 형식 일탈 방지.
- `response.text` 가 None 인 케이스(safety filter, blocked candidates 등) 명시적
  방어 → 식별 가능한 예외로 변환. 호출자가 retry/Failed 분기를 정확히 판단할 수
  있게 한다.
- 파싱 실패 시 raw text 일부를 structlog 에 남겨 디버깅 가능하게.
- 503 등 transient 에러는 SDK 의 ServerError 그대로 위로 전파 → Celery autoretry
  에서 처리.
"""
import json
import re

import structlog
from google import genai
from google.genai import types

from app.retrospective.domain.exceptions.exceptions import (
    SummaryInvalidStateException,
)
from app.retrospective.domain.models.value_objects import SummaryContent
from app.shared.infrastructure.config.ai import AIConfig

_log = structlog.get_logger(__name__)

_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "achievements": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "challenges": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "learnings": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "next_focus": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
    },
    required=["achievements", "challenges", "learnings", "next_focus"],
    property_ordering=["achievements", "challenges", "learnings", "next_focus"],
)


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
                response_schema=_RESPONSE_SCHEMA,
            ),
        )

        text = response.text
        if text is None:
            # safety filter / no candidates / blocked. Celery autoretry 대상이 아님 —
            # 같은 prompt 면 동일 결과. 호출자가 FAILED 마킹하도록 명시 예외.
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

        return self._parse(text)

    def _parse(self, text: str) -> SummaryContent:
        # response_mime_type+response_schema 면 순수 JSON 이지만, SDK 가 가끔
        # ```json ... ``` 로 감쌀 수 있으므로 방어적으로 첫 `{...}` 블록 추출.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        raw = match.group() if match else text
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            _log.warning("gemini.summary.parse_failed", raw_text=text[:500])
            raise

        def _as_str_list(value) -> tuple[str, ...]:
            if not isinstance(value, list):
                return ()
            return tuple(str(item) for item in value if item is not None)

        return SummaryContent(
            achievements=_as_str_list(data.get("achievements")),
            challenges=_as_str_list(data.get("challenges")),
            learnings=_as_str_list(data.get("learnings")),
            next_focus=_as_str_list(data.get("next_focus")),
        )
