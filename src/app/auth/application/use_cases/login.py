from app.auth.application.dtos.commands import LoginCommand
from app.auth.application.services.session_service import RequestMeta, SessionService
from app.auth.domain.exceptions.exceptions import AuthInvalidCredentialsException
from app.shared.infrastructure.auth.jwt import create_access_token
from app.shared.infrastructure.auth.password import verify_password
from app.user.domain.repositories.repository import IUserRepository


class LoginUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        session_service: SessionService,
    ) -> None:
        self._user_repo = user_repo
        self._session_service = session_service

    async def execute(self, cmd: LoginCommand) -> dict[str, str]:
        user = await self._user_repo.find_by_email(cmd.email)
        if not user or not user.password_hash:
            raise AuthInvalidCredentialsException()

        if not verify_password(cmd.password, user.password_hash):
            raise AuthInvalidCredentialsException()

        issued = await self._session_service.issue(
            user.id, RequestMeta(user_agent=cmd.device_info, ip=cmd.ip)
        )
        return {
            "access_token": create_access_token(user.id, user.account_type),
            "refresh_token": issued.refresh_token,
        }
