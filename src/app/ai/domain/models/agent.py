"""LLM 한 차례를 모델과 무관하게 표현하는 값 — Gemini SDK 타입이 응용 계층으로 새지 않게."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    call_id: str | None = None


@dataclass(frozen=True)
class ToolResult:
    name: str
    payload: dict[str, Any]
    call_id: str | None = None


@dataclass(frozen=True)
class ModelMessage:
    role: Literal["user", "model", "tool"]
    text: str | None = None
    calls: tuple[ToolCall, ...] = ()
    results: tuple[ToolResult, ...] = ()
    # model 차례의 원본(모델이 요구하는 서명 등) — 어댑터가 그대로 되돌려 보낸다.
    raw: Any = field(default=None, compare=False)


@dataclass(frozen=True)
class ModelTurn:
    text: str | None
    calls: tuple[ToolCall, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    # 모델이 다음 차례에 그대로 돌려받아야 하는 원본(서명 등) — 어댑터만 해석한다.
    raw: Any = field(default=None, compare=False)
