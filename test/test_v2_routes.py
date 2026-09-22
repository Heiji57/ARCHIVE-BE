"""v2 로 노출되는 GitHub·Calendar·자동 요약 활성 템플릿 엔드포인트.

- GitHub/Calendar: 핸들러는 v1 과 같고, 경로 prefix(/api/v2/)로 세분화된 코드가 나간다.
  (v1 은 _V1_LEGACY_CODES 로 기존 코드 유지 — test_external_io_exception_translation 참고)
- PUT /settings/auto-summary/active: v1 은 알 수 없는 키를 조용히 버려 200 이 나가지만
  (예: 회고 타입명 "yearly" — 요약 타입은 "annual"), v2 는 422 VALIDATION_ERROR.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.github.domain.exceptions.exceptions import GitHubPermissionDeniedException
from app.google_calendar.domain.exceptions.exceptions import CalendarRateLimitedException
from app.main import app
from app.shared.infrastructure.auth.jwt import create_access_token
from app.shared.infrastructure.errors.handler import api_version_of, to_http_response


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v2/github/connection",
        "/api/v2/github/repositories",
        "/api/v2/calendar/connection",
        "/api/v2/calendar/events",
    ],
)
def test_github_and_calendar_are_exposed_under_v2(client, path):
    # 401(인증 필요) 이면 라우트가 존재한다 — 없으면 404.
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    ("exc", "code", "status"),
    [
        (GitHubPermissionDeniedException(), "GITHUB_PERMISSION_DENIED", 403),
        (CalendarRateLimitedException(), "GOOGLE_CALENDAR_RATE_LIMITED", 429),
    ],
)
def test_v2_path_exposes_granular_codes(exc, code, status):
    version = api_version_of("/api/v2/github/repositories")
    response = to_http_response(exc, version)
    assert (response.status_code, json.loads(response.body)["code"]) == (status, code)


def test_v2_active_summary_template_rejects_unknown_key(client):
    token = create_access_token("usr_1")
    response = client.put(
        "/api/v2/settings/auto-summary/active",
        json={"yearly": "tmpl_1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert [d["field"] for d in body["details"]] == ["yearly"]


def test_strict_request_accepts_the_valid_keys():
    from app.retrospective.presentation.requests.template_requests import (
        StrictSetActiveSummaryTemplatesRequest,
    )

    req = StrictSetActiveSummaryTemplatesRequest.model_validate({"annual": None, "weekly": "t"})
    assert req.to_selections() == {"annual": None, "weekly": "t"}


def test_calendar_oauth_callback_exists_only_on_v1(client):
    """callback 은 Google 에 등록된 redirect_uri — v2 경로가 생기면 api.yaml 설명과 어긋난다."""
    paths = set(app.openapi()["paths"])
    assert "/api/v1/calendar/callback" in paths
    assert "/api/v2/calendar/callback" not in paths
