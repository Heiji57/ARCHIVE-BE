"""OAuth provider HTTP 호출 공통 — httpx/응답 형식 오류를 auth 도메인 예외로 번역한다.

provider 응답의 원문(토큰 포함 가능)은 예외 message 에 남기지 않는다 — 상태 코드와
provider 가 준 `error` 식별자만 남긴다.
"""
from typing import Any

import httpx

from app.auth.domain.exceptions.exceptions import (
    OAuthCodeInvalidException,
    OAuthProviderResponseInvalidException,
    OAuthProviderUnavailableException,
)

TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

# authorization code 자체가 무효(만료·재사용·잘못된 값)일 때 provider 가 주는 error.
# 그 외(invalid_client, redirect_uri_mismatch 등)는 우리 설정 문제라 ResponseInvalid.
_CODE_REJECTED_ERRORS = frozenset({"invalid_grant", "bad_verification_code"})


async def send(
    provider: str,
    method: str,
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    **kwargs: Any,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.TransportError as e:
        raise OAuthProviderUnavailableException(
            f"{provider} {method} {url}: {type(e).__name__}"
        ) from e
    if response.status_code >= 500 or response.status_code == 429:
        raise OAuthProviderUnavailableException(
            f"{provider} {method} {url}: HTTP {response.status_code}"
        )
    return response


def parse_json(provider: str, response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as e:
        raise OAuthProviderResponseInvalidException(
            f"{provider} {response.request.url}: non-JSON body (HTTP {response.status_code})"
        ) from e


def token_from_exchange(provider: str, response: httpx.Response) -> str:
    """token 교환 응답 → access_token. GitHub 은 실패도 200 + {"error": ...} 로 준다."""
    data = parse_json(provider, response)
    error = data.get("error") if isinstance(data, dict) else None
    if error in _CODE_REJECTED_ERRORS:
        raise OAuthCodeInvalidException(f"{provider} token exchange: {error}")
    if error or response.status_code >= 400:
        raise OAuthProviderResponseInvalidException(
            f"{provider} token exchange rejected: HTTP {response.status_code} error={error}"
        )
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise OAuthProviderResponseInvalidException(f"{provider} token exchange: no access_token")
    return token


def ensure_ok(provider: str, response: httpx.Response) -> None:
    """token 교환 이외 호출(사용자 정보 등) — 방금 발급받은 토큰으로 4xx 면 provider 쪽 이상."""
    if response.status_code >= 400:
        raise OAuthProviderResponseInvalidException(
            f"{provider} {response.request.url}: HTTP {response.status_code}"
        )
