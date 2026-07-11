from app.auth.application.dtos.commands import LoginCommand
from app.auth.application.services.session_service import RequestMeta, SessionService
from app.auth.domain.exceptions.exceptions import (
    AuthInvalidCredentialsException,
    LoginRateLimitExceededException,
)
from app.auth.infrastructure.cache.login_attempt import LoginAttemptCache
from app.shared.infrastructure.auth.jwt import create_access_token
from app.shared.infrastructure.auth.password import verify_password
from app.user.domain.repositories.repository import IUserRepository


class LoginUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        session_service: SessionService,
        login_attempts: LoginAttemptCache,
    ) -> None:
        self._user_repo = user_repo
        self._session_service = session_service
        self._login_attempts = login_attempts

    async def execute(self, cmd: LoginCommand) -> dict[str, str]:
        if await self._login_attempts.is_locked(cmd.email, cmd.ip):
            raise LoginRateLimitExceededException()

        user = await self._user_repo.find_by_email(cmd.email)
        if not user or not user.password_hash:
            await self._login_attempts.record_failure(cmd.email, cmd.ip)
            raise AuthInvalidCredentialsException()

        if not verify_password(cmd.password, user.password_hash):
            await self._login_attempts.record_failure(cmd.email, cmd.ip)
            raise AuthInvalidCredentialsException()

        await self._login_attempts.reset(cmd.email, cmd.ip)
        issued = await self._session_service.issue(
            user.id, RequestMeta(user_agent=cmd.device_info, ip=cmd.ip)
        )
        return {
            "access_token": create_access_token(user.id, user.account_type),
            "refresh_token": issued.refresh_token,
        }
