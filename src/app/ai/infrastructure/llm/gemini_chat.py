"""ChatModelPort 의 Gemini 구현 — 도구 호출(function calling)을 수동 루프로 쓴다.

자동 함수 호출은 끈다: 도구 실행·제안 저장·SSE 진행 문장은 응용 계층(`agent.run_turn`)이 한다.
모델 차례의 원본 Content 는 `ModelTurn.raw` 로 돌려줘, 다음 요청에 그대로 되돌려 보낸다
(thought signature 등 모델이 요구하는 값을 잃지 않게).
"""

from typing import Any

from google import genai
from google.genai import types

from app.ai.domain.models.agent import ModelMessage, ModelTurn, ToolCall, ToolSpec
from app.shared.infrastructure.ai import errors as ai_errors
from app.shared.infrastructure.ai.usage import log_generate_usage
from app.shared.infrastructure.config.ai import AIConfig


class GeminiChatModel:
    def __init__(self, config: AIConfig) -> None:
        self._client = genai.Client(
            api_key=config.google_api_key,
            http_options=types.HttpOptions(timeout=config.gemini_timeout_ms),
        )
        self._model = config.gemini_model

    async def generate(
        self, system: str, history: list[ModelMessage], tools: list[ToolSpec]
    ) -> ModelTurn:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=t.parameters,
                        )
                        for t in tools
                    ]
                )
            ]
            if tools
            else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        response = await ai_errors.call(
            "gemini.ai.chat",
            self._client.aio.models.generate_content(
                model=self._model, contents=[_to_content(m) for m in history], config=config
            ),
        )
        log_generate_usage("gemini.ai.chat", self._model, response)
        content = response.candidates[0].content if response.candidates else None
        calls = tuple(
            ToolCall(name=fc.name or "", args=dict(fc.args or {}), call_id=fc.id)
            for fc in (response.function_calls or [])
        )
        usage = response.usage_metadata
        return ModelTurn(
            text=response.text if not calls else None,
            calls=calls,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            raw=content,
        )


def _to_content(m: ModelMessage) -> Any:
    if m.role == "model" and m.raw is not None:
        return m.raw
    if m.role == "tool":
        return types.Content(
            role="user",
            parts=[
                types.Part.from_function_response(name=r.name, response=r.payload)
                for r in m.results
            ],
        )
    if m.role == "model":
        parts = [types.Part.from_text(text=m.text)] if m.text else []
        parts += [
            types.Part(function_call=types.FunctionCall(name=c.name, args=c.args, id=c.call_id))
            for c in m.calls
        ]
        return types.Content(role="model", parts=parts)
    return types.Content(role="user", parts=[types.Part.from_text(text=m.text or "")])
