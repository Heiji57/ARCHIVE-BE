"""Refresh token 회전 + reuse detection.

SessionService.rotate() 가 정책의 본체. 본 use case 는 라우터 응답 형태로 어댑트만 한다.

응답 시 refresh_token 이 빈 문자열이면 grace window hit — 호출자는 기존 RT 쿠키를
**갱신하지 않고 그대로** 두면 된다 (라우터에서 분기).
"""
from app.auth.application.services.session_service import (
    RequestMeta,
    SessionService,
)
from app.shared.infrastructure.auth.jwt import create_access_token


class RefreshTokenUseCase:
    def __init__(self, session_service: SessionService) -> None:
        self._session_service = session_service

    async def execute(
        self,
        raw_refresh_token: str,
        device_info: str | None,
        ip: str | None = None,
    ) -> dict[str, str]:
        rotated = await self._session_service.rotate(
            raw_refresh_token, RequestMeta(user_agent=device_info, ip=ip)
        )
        return {
            "access_token": create_access_token(rotated.user_id),
            "refresh_token": rotated.refresh_token,  # "" 면 grace hit
        }
