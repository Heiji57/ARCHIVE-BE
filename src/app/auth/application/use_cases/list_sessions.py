"""활성 세션 목록 조회."""
from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.application.services.session_service import SessionService


@dataclass(frozen=True)
class SessionView:
    session_id: str
    device_label: str | None
    device_info: str | None
    ip_prefix: str | None
    issued_at: datetime
    last_used_at: datetime
    rotation_counter: int
    is_current: bool


class ListSessionsUseCase:
    def __init__(self, session_service: SessionService) -> None:
        self._session_service = session_service

    async def execute(
        self,
        user_id: str,
        current_session_id: str | None,
    ) -> list[SessionView]:
        records = await self._session_service.list_for_user(user_id)
        out: list[SessionView] = []
        for r in records:
            out.append(
                SessionView(
                    session_id=r.session_id,
                    device_label=r.device_label,
                    device_info=r.device_info,
                    ip_prefix=r.ip_prefix,
                    issued_at=datetime.fromtimestamp(r.issued_at, tz=timezone.utc),
                    last_used_at=datetime.fromtimestamp(r.last_used_at, tz=timezone.utc),
                    rotation_counter=r.rotation_counter,
                    is_current=(r.session_id == current_session_id),
                )
            )
        out.sort(key=lambda s: s.last_used_at, reverse=True)
        return out
