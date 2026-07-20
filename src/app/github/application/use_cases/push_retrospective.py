"""사용자 회고 마크다운을 push target 저장소에 commit/push.

폴더/파일명/커밋 메시지는 사용자 settings.locale에 따라 i18n 적용.
파일 경로: {periodFolder}/{filename}.md
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.application.dtos.commands import PushRetrospectiveCommand
from app.github.application.use_cases._token import get_github_access_token
from app.github.domain.exceptions.exceptions import (
    GitHubPushTargetNotSetException,
    GitHubRepositoryNotLinkedException,
)
from app.github.domain.models.retrospective_push import RetrospectivePush
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.domain.repositories.retrospective_push_repository import (
    IRetrospectivePushRepository,
)
from app.github.infrastructure.api.github_api_client import (
    GitHubApiClient,
    GitHubPushResult,
)
from app.github.infrastructure.i18n.path_labels import get_labels
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.utils.id import generate_id

_DAILY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_WEEKLY_RE = re.compile(r"^(\d{4})-(\d{2})-W([1-6])$")
_MONTHLY_RE = re.compile(r"^(\d{4})-(\d{2})$")
_ANNUAL_RE = re.compile(r"^(\d{4})$")


@dataclass(frozen=True)
class PushOutcome:
    commit_sha: str
    html_url: str
    path: str


def _build_path_and_message(
    locale: str, period_type: str, period_key: str
) -> tuple[str, str]:
    """returns (path, commit_message). period_key는 사전 검증됨."""
    labels = get_labels(locale)
    pt = period_type.upper()

    if pt == "DAILY":
        m = _DAILY_RE.fullmatch(period_key)
        assert m is not None
        folder = labels.daily_folder
        filename = labels.daily_filename.format(date=period_key)
        path = f"{folder}/{filename}.md"
        msg_key = period_key
    elif pt == "WEEKLY":
        m = _WEEKLY_RE.fullmatch(period_key)
        assert m is not None
        year, month, week = int(m.group(1)), int(m.group(2)), int(m.group(3))
        folder = labels.weekly_folder
        filename = labels.weekly_filename.format(year=year, month=month, week=week)
        path = f"{folder}/{filename}.md"
        msg_key = period_key
    elif pt == "MONTHLY":
        m = _MONTHLY_RE.fullmatch(period_key)
        assert m is not None
        year, month = int(m.group(1)), int(m.group(2))
        folder = labels.monthly_folder
        filename = labels.monthly_filename.format(year=year, month=month)
        path = f"{folder}/{filename}.md"
        msg_key = period_key
    elif pt == "ANNUAL":
        m = _ANNUAL_RE.fullmatch(period_key)
        assert m is not None
        year = int(m.group(1))
        folder = labels.annual_folder
        filename = labels.annual_filename.format(year=year)
        path = f"{folder}/{filename}.md"
        msg_key = period_key
    else:
        raise ValueError(f"Unsupported period_type: {period_type}")

    commit_message = f"docs(retro): {filename} {msg_key}"
    return path, commit_message


def validate_period_key(period_type: str, period_key: str) -> bool:
    pt = period_type.upper()
    if pt == "DAILY":
        return _DAILY_RE.fullmatch(period_key) is not None
    if pt == "WEEKLY":
        return _WEEKLY_RE.fullmatch(period_key) is not None
    if pt == "MONTHLY":
        return _MONTHLY_RE.fullmatch(period_key) is not None
    if pt == "ANNUAL":
        return _ANNUAL_RE.fullmatch(period_key) is not None
    return False


class PushRetrospectiveUseCase:
    def __init__(
        self,
        settings_repo: IUserSettingsRepository,
        oauth_repo: IOAuthConnectionRepository,
        repo: IGitHubRepositoryRepository,
        api_client: GitHubApiClient,
        push_repo: IRetrospectivePushRepository,
    ) -> None:
        self._settings_repo = settings_repo
        self._oauth_repo = oauth_repo
        self._repo = repo
        self._api_client = api_client
        self._push_repo = push_repo

    async def execute(self, cmd: PushRetrospectiveCommand) -> PushOutcome:
        settings = await self._settings_repo.find_by_user_id(cmd.user_id)
        if settings is None or settings.github_push_target_repository_id is None:
            raise GitHubPushTargetNotSetException(
                "Configure push target repository first."
            )

        target = await self._repo.find_by_id(
            settings.github_push_target_repository_id, cmd.user_id
        )
        if target is None:
            # FK SET NULL이 적용되지 않은 race condition 가능성 — 일관성 처리
            raise GitHubRepositoryNotLinkedException(
                "Push target repository is no longer linked."
            )

        access_token = await get_github_access_token(self._oauth_repo, cmd.user_id)

        path, commit_message_prefix = _build_path_and_message(
            settings.locale, cmd.period_type, cmd.period_key
        )

        # 기존 파일 sha 조회 (update 시 필요)
        existing_sha = await self._api_client.get_file_sha(
            access_token=access_token,
            owner=target.owner,
            name=target.name,
            path=path,
            branch=target.default_branch,
        )

        # 커밋 메시지: add (신규) vs update (갱신)
        action = "update" if existing_sha else "add"
        commit_message = self._format_commit_message(
            settings.locale, action, cmd.period_type, cmd.period_key
        )

        result: GitHubPushResult = await self._api_client.put_file(
            access_token=access_token,
            owner=target.owner,
            name=target.name,
            path=path,
            content_bytes=cmd.content_markdown.encode("utf-8"),
            message=commit_message,
            branch=target.default_branch,
            sha=existing_sha,
        )

        # period_type 정규화 — JournalEntry 의 'yearly' 와 push API 의 'annual' 표기 차이 흡수
        normalized_period_type = cmd.period_type.lower()
        if normalized_period_type == "yearly":
            normalized_period_type = "annual"

        now = datetime.now(timezone.utc)
        await self._push_repo.upsert(
            RetrospectivePush(
                id=generate_id("rp"),
                user_id=cmd.user_id,
                period_type=normalized_period_type,
                period_key=cmd.period_key,
                repository_id=target.id,
                repository_full_name=target.full_name,
                path=result.path,
                commit_sha=result.commit_sha,
                html_url=result.html_url,
                pushed_at=now,
                created_at=now,
            )
        )

        return PushOutcome(
            commit_sha=result.commit_sha,
            html_url=result.html_url,
            path=result.path,
        )

    def _format_commit_message(
        self, locale: str, action: str, period_type: str, period_key: str
    ) -> str:
        """언어별 커밋 메시지. prefix `docs(retro):` 는 영문 고정."""
        pt_lower = period_type.lower()
        if locale == "ko":
            ko_action = "추가" if action == "add" else "갱신"
            ko_type = {
                "daily": "일간",
                "weekly": "주간",
                "monthly": "월간",
                "annual": "년간",
            }.get(pt_lower, pt_lower)
            return f"docs(retro): {ko_type} {period_key} 회고록 {ko_action}"
        # en (fallback)
        return f"docs(retro): {action} {pt_lower} {period_key} retrospective"
