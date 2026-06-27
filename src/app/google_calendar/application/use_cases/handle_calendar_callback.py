from datetime import datetime, timedelta, timezone

from app.google_calendar.domain.models.calendar_connection import GoogleCalendarConnection
from app.google_calendar.domain.repositories.repository import (
    IGoogleCalendarConnectionRepository,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (
    GoogleCalendarApiClient,
)
from app.google_calendar.infrastructure.cache.calendar_state import (
    CalendarOAuthStateCache,
)
from app.shared.domain.utils.id import generate_id


class HandleCalendarCallbackUseCase:
    """Google Calendar OAuth callback 처리.

    code → refresh_token 교환 후 connection upsert. 이미 연결돼 있으면 토큰 갱신
    (재연결 = 토큰 회전 + needs_reauth 해제). 기존 sync_token 은 유지하지 않고
    재연결 시 비워 full resync 를 유도한다.
    """

    def __init__(
        self,
        api_client: GoogleCalendarApiClient,
        state_cache: CalendarOAuthStateCache,
        connection_repo: IGoogleCalendarConnectionRepository,
    ) -> None:
        self._api_client = api_client
        self._state_cache = state_cache
        self._connection_repo = connection_repo

    async def execute(self, code: str, state: str) -> None:
        user_id = await self._state_cache.consume_state(state)

        tokens = await self._api_client.exchange_code(code)
        google_user_id = await self._api_client.get_user_id(tokens.access_token)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=tokens.expires_in)

        existing = await self._connection_repo.find_by_user_id(user_id)
        if existing is not None:
            existing.google_user_id = google_user_id
            existing.access_token = tokens.access_token
            # 재동의 시 refresh_token 이 항상 재발급되지만(prompt=consent), 누락 대비 보존.
            if tokens.refresh_token:
                existing.refresh_token = tokens.refresh_token
            existing.token_expires_at = expires_at
            existing.scope = self._api_client.scope
            existing.sync_token = None  # 재연결 → full resync
            existing.needs_reauth = False
            existing.updated_at = now
            await self._connection_repo.save(existing)
            return

        connection = GoogleCalendarConnection(
            id=generate_id("gcal"),
            user_id=user_id,
            google_user_id=google_user_id,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token or "",
            token_expires_at=expires_at,
            scope=self._api_client.scope,
            sync_token=None,
            last_synced_at=None,
            needs_reauth=False,
            created_at=now,
        )
        await self._connection_repo.save(connection)
