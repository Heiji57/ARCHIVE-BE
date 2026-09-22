"""서버 로그로 에러를 추적할 수 있는지 — 실제 JSON 출력 줄을 검증한다.

이전 상태:
- 전역 핸들러가 로그를 전혀 남기지 않았고, 외부 API 오류의 상태코드·응답 요약(exc.message)은
  응답에도 로그에도 없이 버려졌다.
- 처리되지 않은 예외는 Starlette 기본 500(평문)으로 나가 FE 봉투가 깨졌다.
- 요청 상관관계 ID 가 없어 한 요청의 로그를 묶을 수 없었다.
- structlog 설정이 security logger 를 처음 가져올 때만 일어나 포맷이 제각각이었다.
"""
import io
import json
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.shared.domain.exceptions.external import AIServiceUnavailableException
from app.shared.infrastructure.logger.request_context import RequestContextMiddleware
from app.shared.infrastructure.logger.setup import configure_logging


@pytest.fixture
def buffer_handler():
    configure_logging()
    root = logging.getLogger()
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(root.handlers[0].formatter)
    root.addHandler(handler)

    def read() -> list[dict]:
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]

    try:
        yield read
    finally:
        root.removeHandler(handler)


def _app() -> FastAPI:
    from app.shared.infrastructure.auth.jwt import get_current_user

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("unexpected bug")

    @app.get("/me")
    async def me(user=Depends(get_current_user)):
        import structlog

        structlog.get_logger("probe").error("probe.after_auth")
        return {"ok": True}

    return app


def test_unhandled_exception_is_logged_with_request_id_and_enveloped(buffer_handler):
    client = TestClient(_app(), raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "status": "error", "code": "INTERNAL_ERROR", "data": None, "details": [],
    }
    request_id = response.headers["x-request-id"]

    [line] = [ln for ln in buffer_handler() if ln["event"] == "http.unhandled_exception"]
    assert line["level"] == "error"
    assert line["request_id"] == request_id
    assert (line["method"], line["path"]) == ("GET", "/boom")
    assert "RuntimeError: unexpected bug" in line["exception"], "traceback 이 남아야 원인을 찾는다"


@pytest.mark.parametrize(
    ("incoming", "echoed"),
    [("abc-123_X.y", True), ("bad\nvalue", False), ("x" * 65, False)],
)
def test_request_id_header_is_echoed_only_when_safe(incoming, echoed):
    client = TestClient(_app(), raise_server_exceptions=False)
    response = client.get("/boom", headers={"x-request-id": incoming})
    assert (response.headers["x-request-id"] == incoming) is echoed


def test_user_id_is_bound_after_authentication(buffer_handler):
    from app.shared.infrastructure.auth.jwt import create_access_token

    client = TestClient(_app())
    token = create_access_token("usr_42")
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    [line] = [ln for ln in buffer_handler() if ln["event"] == "probe.after_auth"]
    assert line["user_id"] == "usr_42"
    assert "request_id" in line


def test_5xx_domain_error_logs_message_and_cause(buffer_handler):
    from app.shared.infrastructure.errors.handler import log_error_response

    try:
        try:
            raise TimeoutError("gemini read timeout")
        except TimeoutError as cause:
            raise AIServiceUnavailableException("gemini.embed: ReadTimeout") from cause
    except AIServiceUnavailableException as exc:
        log_error_response(exc, 503)

    [line] = [ln for ln in buffer_handler() if ln["event"] == "http.error_response"]
    assert line["level"] == "error"
    assert line["error"] == "gemini.embed: ReadTimeout"
    assert "TimeoutError: gemini read timeout" in line["exception"], "원인 체인이 남아야 한다"


def test_security_statuses_warn_and_plain_4xx_is_silent(buffer_handler):
    from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
    from app.shared.infrastructure.errors.handler import log_error_response
    from app.todo.domain.exceptions.exceptions import TodoNotFoundException

    log_error_response(AuthTokenInvalidException(), 401)
    log_error_response(TodoNotFoundException(), 404)

    lines = buffer_handler()
    rejected = [ln for ln in lines if ln["event"] == "http.request_rejected"]
    assert len(rejected) == 1
    assert (rejected[0]["level"], rejected[0]["logger"], rejected[0]["code"]) == (
        "warning", "security", "AUTH_TOKEN_INVALID",
    )
    assert not any(ln.get("code") == "TODO_NOT_FOUND" for ln in lines), "정상 4xx 는 노이즈"


def test_logging_setup_silences_url_logging_libraries():
    """httpx INFO 로그는 URL 전체(쿼리 포함)를 남긴다 — syncToken 등이 새지 않게."""
    configure_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("uvicorn.access").handlers == []
