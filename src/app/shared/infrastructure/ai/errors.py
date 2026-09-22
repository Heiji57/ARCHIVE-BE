"""google-genai / httpx 예외 → shared AI 도메인 예외 번역."""
from collections.abc import Awaitable

import httpx
from google.genai import errors as genai_errors

from app.shared.domain.exceptions.external import (
    AIQuotaExceededException,
    AIRequestRejectedException,
    AIServiceException,
    AIServiceUnavailableException,
)


def translate(exc: Exception, operation: str) -> AIServiceException | None:
    """번역 대상이 아니면 None — 호출부가 원본을 그대로 전파한다(코드 버그 은폐 방지)."""
    if isinstance(exc, genai_errors.ServerError):
        return AIServiceUnavailableException(f"{operation}: HTTP {exc.code} {exc.status}")
    if isinstance(exc, genai_errors.ClientError):
        if exc.code == 429:
            return AIQuotaExceededException(f"{operation}: HTTP 429 {exc.status}")
        return AIRequestRejectedException(f"{operation}: HTTP {exc.code} {exc.status}")
    if isinstance(exc, genai_errors.UnknownApiResponseError):
        return AIServiceUnavailableException(f"{operation}: unparseable API response")
    if isinstance(exc, httpx.TransportError):
        return AIServiceUnavailableException(f"{operation}: {type(exc).__name__}")
    return None


async def call[T](operation: str, awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except (
        genai_errors.APIError,
        genai_errors.UnknownApiResponseError,
        httpx.TransportError,
    ) as e:
        translated = translate(e, operation)
        if translated is None:
            raise
        raise translated from e
