"""설정 섹션별 PATCH — 보낸 필드만 바뀌고 나머지는 그대로다.

예전 `PUT /settings` 는 전체 교체라, FE 가 `github` 를 빼고 다른 설정을 저장하면
GitHub push 대상 저장소가 null 로 지워졌다. 섹션 PATCH 는 다른 섹션 값을 건드리지 않는다.
"""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.github.domain.exceptions.exceptions import GitHubRepositoryNotLinkedException
from app.main import app
from app.settings.application.dtos.commands import PatchSettingsCommand
from app.settings.application.use_cases.patch_settings import PatchSettingsUseCase
from app.settings.domain.models.user_settings import UserSettings
from app.settings.presentation.requests.requests import (
    AutoSummarySettingsPatchRequest,
    CalendarSettingsPatchRequest,
    GeneralSettingsPatchRequest,
    GitHubSettingsPatchRequest,
    NotificationSettingsPatchRequest,
)


class _FakeSettingsRepo:
    def __init__(self, settings: UserSettings | None) -> None:
        self.settings = settings

    async def find_by_user_id(self, user_id: str) -> UserSettings | None:
        return self.settings

    async def save(self, settings: UserSettings) -> UserSettings:
        self.settings = settings
        return settings


class _FakeGitHubRepo:
    def __init__(self, linked_ids: set[str]) -> None:
        self._linked = linked_ids

    async def find_by_id(self, repo_id: str, user_id: str):
        return SimpleNamespace(id=repo_id) if repo_id in self._linked else None


def _existing() -> UserSettings:
    return UserSettings(
        user_id="usr_1",
        locale="en",
        auto_summary_weekly=True,
        notification_retention_days=90,
        calendar_auto_push_todo=True,
        github_push_target_repository_id="repo_1",
    )


def _use_case(settings: UserSettings | None, linked: set[str] | None = None):
    repo = _FakeSettingsRepo(settings)
    return PatchSettingsUseCase(repo, _FakeGitHubRepo(linked or {"repo_1", "repo_2"})), repo


async def test_patch_changes_only_provided_fields():
    use_case, _ = _use_case(_existing())
    result = await use_case.execute(PatchSettingsCommand(user_id="usr_1", locale="ko"))

    assert result.locale == "ko"
    assert result.auto_summary_weekly is True
    assert result.notification_retention_days == 90
    assert result.calendar_auto_push_todo is True
    assert result.github_push_target_repository_id == "repo_1"
    assert result.updated_at is not None


async def test_patch_creates_defaults_for_new_user():
    use_case, repo = _use_case(None)
    result = await use_case.execute(
        PatchSettingsCommand(user_id="usr_1", auto_summary_monthly=True)
    )
    assert result.auto_summary_monthly is True
    assert result.locale == "ko"
    assert repo.settings is result


async def test_github_null_clears_push_target():
    use_case, _ = _use_case(_existing())
    result = await use_case.execute(
        PatchSettingsCommand(user_id="usr_1", github_push_target_repository_id=None)
    )
    assert result.github_push_target_repository_id is None


async def test_github_unlinked_repository_is_rejected():
    use_case, repo = _use_case(_existing(), linked={"repo_1"})
    with pytest.raises(GitHubRepositoryNotLinkedException):
        await use_case.execute(
            PatchSettingsCommand(user_id="usr_1", github_push_target_repository_id="repo_x")
        )
    assert repo.settings.github_push_target_repository_id == "repo_1"


def test_request_provided_contains_only_sent_fields():
    req = AutoSummarySettingsPatchRequest.model_validate({"autoSummaryWeekly": False})
    assert req.provided() == {"auto_summary_weekly": False}

    assert GeneralSettingsPatchRequest.model_validate({}).provided() == {}


def test_locale_is_normalized():
    req = GeneralSettingsPatchRequest.model_validate({"locale": " EN "})
    assert req.provided() == {"locale": "en"}


@pytest.mark.parametrize(
    ("model", "body"),
    [
        (GeneralSettingsPatchRequest, {"locale": None}),
        (AutoSummarySettingsPatchRequest, {"autoSummaryYearly": None}),
        (NotificationSettingsPatchRequest, {"notificationRetentionDays": None}),
        (CalendarSettingsPatchRequest, {"calendarAutoDeleteTodo": None}),
    ],
)
def test_null_rejected_for_non_nullable_fields(model, body):
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_retention_days_range():
    with pytest.raises(ValidationError):
        NotificationSettingsPatchRequest.model_validate({"notificationRetentionDays": 0})


def test_github_null_is_allowed_in_request():
    req = GitHubSettingsPatchRequest.model_validate({"pushTargetRepositoryId": None})
    assert req.provided() == {"push_target_repository_id": None}


def test_settings_routes():
    paths = app.openapi()["paths"]
    for section in ("general", "auto-summary", "notifications", "calendar", "github"):
        assert "patch" in paths[f"/api/v1/settings/{section}"]
    assert set(paths["/api/v1/settings"]) == {"get"}
