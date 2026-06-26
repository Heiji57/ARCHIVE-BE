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

def _array_field(description: str) -> types.Schema:
    return types.Schema(
        type=types.Type.ARRAY,
        items=types.Schema(type=types.Type.STRING),
        description=description,
    )


_FIXED_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "achievements": _array_field(
            "Concrete accomplishments and completed work. Max 5 items."
        ),
        "challenges": _array_field(
            "Difficulties, blockers, or problems faced. Max 5 items."
        ),
        "learnings": _array_field(
            "Insights, lessons, or new knowledge gained. Max 5 items."
        ),
        "next_focus": _array_field(
            "Priorities or action items for the next period. Max 5 items."
        ),
    },
    required=["achievements", "challenges", "learnings", "next_focus"],
    property_ordering=["achievements", "challenges", "learnings", "next_focus"],
)


class GeminiSummaryClient:
    def __init__(self, config: AIConfig) -> None:
        # http_options.timeout 은 밀리초. 응답이 없으면 무한 대기 대신 타임아웃 →
        # 워커가 hang 된 호출에 묶이는 것을 방지 (한 건의 stall 이 큐 전체를 막던 문제).
        self._client = genai.Client(
            api_key=config.google_api_key,
            http_options=types.HttpOptions(timeout=config.gemini_timeout_ms),
        )
        self._model = config.gemini_model

    async def generate(
        self, prompt: str, response_schema: types.Schema | None = None
    ) -> SummaryContent:
        """AI 요약 생성.

        response_schema 가 주어지면(사용자 템플릿 헤딩 기반 동적 스키마) 그것을,
        없으면 고정 4-key 스키마를 강제한다. 어느 경로든 항상 스키마를 적용해
        키 구조가 Gemini 디코딩 단계에서 보장된다 — 키 변형/누락/조용한 드롭 방지.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema or _FIXED_RESPONSE_SCHEMA,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
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
        # response_mime_type 사용 시 순수 JSON 이지만, SDK 가 가끔
        # ```json ... ``` 로 감쌀 수 있으므로 방어적으로 첫 `{...}` 블록 추출.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        raw = match.group() if match else text
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            _log.warning("gemini.summary.parse_failed", raw_text=text[:500])
            raise

        sections = {
            k: [str(item) for item in v if item is not None]
            for k, v in data.items()
            if isinstance(v, list)
        }
        return SummaryContent(sections=sections)
