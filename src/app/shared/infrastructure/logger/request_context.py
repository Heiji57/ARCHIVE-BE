"""요청 단위 로그 컨텍스트 + 처리되지 않은 예외의 최후 경계.

순수 ASGI 미들웨어 — BaseHTTPMiddleware 는 하위 앱을 별도 task 로 돌려 contextvars 전파가
어긋날 수 있다. 여기서 바인딩한 값(request_id, method, path, client_ip)은 이후 모든 로그 줄에
자동으로 붙고, 인증 의존성이 user_id 를 덧붙인다(`shared/infrastructure/auth/jwt.py`).

처리되지 않은 예외는 여기서 traceback 과 함께 error 로 남기고 공통 에러 봉투로 응답한다 —
Starlette 기본 500(평문, 로그 포맷 제각각)을 대체한다. CORS 미들웨어보다 안쪽에 둬야 이 500
응답에도 CORS 헤더가 붙어 FE 가 에러 본문을 읽을 수 있다.
"""
import json
import re
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_log = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"
# 클라이언트가 보낸 값은 로그 주입 방지를 위해 형식을 제한한다.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


def _client_ip(scope: Scope) -> str | None:
    xff = _header(scope, b"x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = scope.get("client")
    return str(client[0]) if client else None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, REQUEST_ID_HEADER.encode())
        valid = incoming is not None and _VALID_REQUEST_ID.match(incoming) is not None
        request_id = incoming if valid and incoming else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=scope.get("method"),
            path=scope.get("path"),
            client_ip=_client_ip(scope),
        )

        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # 최후 경계 — 도메인 예외로 번역되지 않고 여기까지 온 것은 코드 버그다.
            _log.exception("http.unhandled_exception")
            if response_started:
                raise  # 스트리밍(SSE 등) 도중 — 응답을 새로 쓸 수 없다
            body = json.dumps(
                {"status": "error", "code": "INTERNAL_ERROR", "data": None, "details": []}
            ).encode()
            await send_with_request_id({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
