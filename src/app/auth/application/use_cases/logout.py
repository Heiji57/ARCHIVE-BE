"""Logout — sessionId 기반 단일 세션 폐기."""
from app.auth.application.services.session_service import SessionService
from app.auth.domain.exceptions.exceptions import RefreshTokenInvalidException


class LogoutUseCase:
    def __init__(self, session_service: SessionService) -> None:
        self._session_service = session_service

    async def execute(self, user_id: str, raw_refresh_token: str) -> None:
        session_id = await self._session_service.get_session_id_from_rt(
            raw_refresh_token
        )
        if not session_id:
            raise RefreshTokenInvalidException()
        await self._session_service.revoke(session_id, user_id)
