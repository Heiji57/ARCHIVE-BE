"""계정 삭제 — soft delete(01 §3).

두 단계로 나눈다 — Redis·파일·외부 작업은 DB 커밋 뒤에만(롤백되면 아무것도 바뀌지 않게).
1. `DeleteAccountUseCase`(요청 트랜잭션): users.deleted_at, OAuth·Google Calendar 연결 행 삭제
   (같은 GitHub·Google 계정으로 다시 가입할 수 있게), 프로필 사진 키 비우기.
2. `FinishAccountDeletionUseCase`(커밋 뒤, 라우터 BackgroundTasks): 모든 refresh 세션 폐기,
   남은 access token 표식, 사진 파일 삭제, 외부 토큰 철회 작업.
데이터는 30일 뒤 worker.purge_deleted_accounts 가 지운다.
"""

import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from app.auth.application.ports import (
    AvatarStorage,
    DeletedAccountMarker,
    ExternalToken,
    ExternalTokenRevoker,
)
from app.auth.application.services.session_service import SessionService
from app.auth.domain.exceptions.exceptions import (
    AccountDeleteConfirmMismatchException,
    ReauthRequiredException,
)
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.google_calendar.domain.repositories.repository import (
    IGoogleCalendarConnectionRepository,
)
from app.shared.domain.context.user_context import UserContext
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.repositories.repository import IUserRepository

REAUTH_WINDOW_SECONDS = 600


@dataclass(frozen=True)
class DeletedAccount:
    """커밋 뒤 단계에 넘길 것."""

    user_id: str
    avatar_key: str | None = None
    tokens: list[ExternalToken] = field(default_factory=list)


class DeleteAccountUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        oauth_repo: IOAuthConnectionRepository,
        calendar_repo: IGoogleCalendarConnectionRepository,
    ) -> None:
        self._user_repo = user_repo
        self._oauth_repo = oauth_repo
        self._calendar_repo = calendar_repo

    async def execute(
        self, current: UserContext, confirm: str, now: float | None = None
    ) -> DeletedAccount:
        now = now if now is not None else time.time()
        # "최근 로그인" = 자격 증명을 확인한 시각(auth_time). refresh 로는 갱신되지 않는다.
        if current.auth_time is None or now - current.auth_time > REAUTH_WINDOW_SECONDS:
            raise ReauthRequiredException()
        user = await self._user_repo.find_by_id(current.id)
        if user is None:
            raise UserNotFoundException()
        # 확인 값 = 표시 이름(그대로) 또는 이메일(대소문자 무시).
        given = confirm.strip()
        by_name = bool(user.display_name) and given == user.display_name
        by_email = given.lower() == str(user.email).lower()
        if not given or not (by_name or by_email):
            raise AccountDeleteConfirmMismatchException()

        tokens: list[ExternalToken] = []
        for conn in await self._oauth_repo.find_by_user_id(user.id):
            tokens.append(ExternalToken(conn.provider.value, conn.access_token))
            await self._oauth_repo.delete(conn.id)
        calendar = await self._calendar_repo.find_by_user_id(user.id)
        if calendar is not None:
            tokens.append(ExternalToken("google", calendar.refresh_token))
            await self._calendar_repo.delete_by_user_id(user.id)

        if user.avatar_key:  # 공개 경로로 서빙되는 사진은 30일 기다리지 않고 바로 내린다
            await self._user_repo.save(replace(user, avatar_key=None, updated_at=datetime.now(UTC)))
        await self._user_repo.soft_delete(user.id)
        return DeletedAccount(user.id, user.avatar_key, tokens)


class FinishAccountDeletionUseCase:
    """커밋 뒤 — 실패해도 계정은 이미 지워졌다(세션이 남으면 refresh 가 사용자 조회에서 막힌다)."""

    def __init__(
        self,
        session_service: SessionService,
        marker: DeletedAccountMarker,
        storage: AvatarStorage,
        revoker: ExternalTokenRevoker,
    ) -> None:
        self._sessions = session_service
        self._marker = marker
        self._storage = storage
        self._revoker = revoker

    async def execute(self, deleted: DeletedAccount) -> None:
        await self._marker.mark(deleted.user_id)
        await self._sessions.revoke_all(deleted.user_id)
        if deleted.avatar_key:
            await self._storage.remove(deleted.avatar_key)
        if deleted.tokens:
            await self._revoker.enqueue(deleted.tokens)
