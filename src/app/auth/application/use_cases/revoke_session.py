"""세션 폐기 (단일 / 현재 외 전부)."""
from app.auth.application.services.session_service import SessionService
from app.auth.domain.exceptions.exceptions import SessionNotFoundException
from app.auth.infrastructure.cache.auth_token import AuthTokenCache


class RevokeSessionUseCase:
    def __init__(
        self,
        session_service: SessionService,
        cache: AuthTokenCache,
    ) -> None:
        self._session_service = session_service
        self._cache = cache

    async def execute(self, user_id: str, session_id: str) -> None:
        record = await self._cache.get(session_id)
        if record is None or record.user_id != user_id:
            raise SessionNotFoundException()
        await self._session_service.revoke(session_id, user_id)


class RevokeOtherSessionsUseCase:
    def __init__(self, session_service: SessionService) -> None:
        self._session_service = session_service

    async def execute(self, user_id: str, current_session_id: str) -> int:
        return await self._session_service.revoke_others(user_id, current_session_id)
