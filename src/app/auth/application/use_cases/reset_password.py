"""비밀번호 재설정 확정.

흐름:
1. 토큰 검증 + user_id 획득 (1회용 — getdel)
2. 사용자 조회 + OAuth 전용 사용자 차단
3. password_hash 갱신
4. 모든 세션 폐기 (모든 기기에서 강제 로그아웃)
"""
from datetime import datetime, timezone

from app.auth.application.dtos.commands import ResetPasswordCommand
from app.auth.application.services.session_service import SessionService
from app.auth.domain.exceptions.exceptions import PasswordResetNotAllowedException
from app.auth.infrastructure.cache.password_reset import PasswordResetCache
from app.shared.infrastructure.auth.password import hash_password
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.repositories.repository import IUserRepository


class ResetPasswordUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        cache: PasswordResetCache,
        session_service: SessionService,
    ) -> None:
        self._user_repo = user_repo
        self._cache = cache
        self._session_service = session_service

    async def execute(self, cmd: ResetPasswordCommand) -> None:
        user_id = await self._cache.consume_token(cmd.token)

        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise UserNotFoundException()
        if user.password_hash is None:
            raise PasswordResetNotAllowedException(
                "OAuth-only users have no password to reset."
            )

        user.password_hash = hash_password(cmd.new_password)
        user.updated_at = datetime.now(timezone.utc)
        await self._user_repo.save(user)

        await self._session_service.revoke_all(user_id)
