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
from app.todo.domain.repositories.repository import ITodoRepository


class HandleCalendarCallbackUseCase:
    """Google Calendar OAuth callback 처리.

    code → refresh_token 교환 후 connection upsert. 이미 연결돼 있으면 토큰 갱신
    (재연결 = 토큰 회전 + needs_reauth 해제). 기존 sync_token 은 유지하지 않고
    재연결 시 비워 full resync 를 유도한다. 재연결 시 failed 로 소진된 todo push
    재시도 카운트를 리셋해, 재연결만으로 밀린 push 가 재개되게 한다.

    처리한 user_id 를 반환한다 — 라우터가 즉시 sync/push 사이클을 재구동하도록.
    """

    def __init__(
        self,
        api_client: GoogleCalendarApiClient,
        state_cache: CalendarOAuthStateCache,
        connection_repo: IGoogleCalendarConnectionRepository,
        todo_repo: ITodoRepository,
    ) -> None:
        self._api_client = api_client
        self._state_cache = state_cache
        self._connection_repo = connection_repo
        self._todo_repo = todo_repo

    async def execute(self, code: str, state: str) -> str:
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
            existing.last_active_at = now  # 방금 연결 = 활성 (백그라운드 sync 대상)
            existing.updated_at = now
            await self._connection_repo.save(existing)
            # 재연결 → failed 로 소진된 push 재시도 카운트 리셋(재연결만으로 재개).
            await self._todo_repo.reset_failed_retry_counts(user_id)
            return user_id

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
            last_active_at=now,  # 방금 연결 = 활성 (백그라운드 sync 대상)
            needs_reauth=False,
            created_at=now,
        )
        await self._connection_repo.save(connection)
        return user_id
