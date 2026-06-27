"""Google Calendar API + OAuth 토큰 클라이언트.

단일 long-lived httpx.AsyncClient 재사용 (커넥션 풀링) — APP scope 로 dishka 등록,
lifespan 종료 시 `close()`.

설계:
- OAuth 토큰 교환/갱신과 Calendar v3 events.list 를 한 곳에서 처리.
- 증분 동기화(`syncToken`) 우선. syncToken 만료(410 GONE) 시 `CalendarSyncTokenExpiredError`
  를 던져 use case 가 full resync 하도록 한다.
- refresh_token 이 무효(`invalid_grant`) 면 `CalendarReauthRequiredException` 으로 변환 —
  use case 가 connection.needs_reauth 로 마킹하고 FE 가 재연결 유도.
"""
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

import httpx

from app.google_calendar.domain.exceptions.exceptions import (
    CalendarApiUnavailableException,
    CalendarReauthRequiredException,
)
from app.shared.infrastructure.config.oauth import GoogleCalendarConfig

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
_PRIMARY_CALENDAR = "primary"
_PAGE_SIZE = 2500
_MAX_PAGES = 20

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


class CalendarSyncTokenExpiredError(Exception):
    """syncToken 이 만료/무효(410 GONE) — full resync 필요. use case 내부 신호."""


@dataclass(frozen=True)
class CalendarTokenBundle:
    access_token: str
    refresh_token: str | None
    expires_in: int


@dataclass(frozen=True)
class RawCalendarEvent:
    google_event_id: str
    calendar_id: str
    title: str
    description: str | None
    location: str | None
    start_at: datetime | None
    end_at: datetime | None
    all_day: bool
    date_key: str
    timezone: str | None
    status: str
    html_link: str | None


@dataclass(frozen=True)
class CalendarEventsPage:
    events: list[RawCalendarEvent]
    next_sync_token: str | None


def _parse_event(item: dict, calendar_id: str) -> RawCalendarEvent | None:
    """Google events.list item → RawCalendarEvent.

    cancelled 이벤트는 id/status 만 있을 수 있어 그대로 통과시킨다(use case 가 삭제 처리).
    date_key 없는 비정상 항목은 None 반환(스킵).
    """
    status = item.get("status", "confirmed")
    event_id = item.get("id")
    if not event_id:
        return None

    start = item.get("start") or {}
    end = item.get("end") or {}

    # cancelled 이벤트는 start/end 가 없을 수 있음 — 삭제 처리용 최소 정보만.
    if status == "cancelled" and not start:
        return RawCalendarEvent(
            google_event_id=event_id,
            calendar_id=calendar_id,
            title=item.get("summary") or "",
            description=None,
            location=None,
            start_at=None,
            end_at=None,
            all_day=False,
            date_key="",
            timezone=None,
            status="cancelled",
            html_link=None,
        )

    all_day = "date" in start
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None

    if all_day:
        date_key = start.get("date", "")
    else:
        start_dt_raw = start.get("dateTime")
        if not start_dt_raw:
            return None
        start_at = datetime.fromisoformat(start_dt_raw)
        date_key = start_at.date().isoformat()
        timezone = start.get("timeZone")
        end_dt_raw = end.get("dateTime")
        if end_dt_raw:
            end_at = datetime.fromisoformat(end_dt_raw)

    if not date_key:
        return None

    return RawCalendarEvent(
        google_event_id=event_id,
        calendar_id=calendar_id,
        title=item.get("summary") or "(No title)",
        description=item.get("description"),
        location=item.get("location"),
        start_at=start_at,
        end_at=end_at,
        all_day=all_day,
        date_key=date_key,
        timezone=timezone,
        status=status,
        html_link=item.get("htmlLink"),
    )


class GoogleCalendarApiClient:
    def __init__(self, config: GoogleCalendarConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def scope(self) -> str:
        return self._config.calendar_scope

    # ── OAuth ────────────────────────────────────────────────────────────────

    def build_authorize_url(self, state: str) -> str:
        params = urlencode({
            "client_id": self._config.client_id,
            "redirect_uri": self._config.calendar_redirect_uri,
            "response_type": "code",
            "scope": self._config.calendar_scope,
            "state": state,
            # refresh_token 확보를 위해 offline + 매번 동의(consent) 강제.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        })
        return f"{_AUTH_URL}?{params}"

    async def exchange_code(self, code: str) -> CalendarTokenBundle:
        response = await self._client.post(
            _TOKEN_URL,
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "code": code,
                "redirect_uri": self._config.calendar_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if response.status_code >= 400:
            raise CalendarReauthRequiredException(
                f"Token exchange failed: {response.text[:200]}"
            )
        data = response.json()
        return CalendarTokenBundle(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def refresh_access_token(self, refresh_token: str) -> CalendarTokenBundle:
        response = await self._client.post(
            _TOKEN_URL,
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code >= 400:
            # invalid_grant 등 → refresh_token 무효, 사용자 재연결 필요.
            raise CalendarReauthRequiredException(
                f"Token refresh failed: {response.text[:200]}"
            )
        data = response.json()
        return CalendarTokenBundle(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def get_user_id(self, access_token: str) -> str:
        response = await self._client.get(
            _USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise CalendarReauthRequiredException("Failed to fetch Google user info.")
        return response.json()["id"]

    # ── Calendar ───────────────────────────────────────────────────────────────

    async def list_events(
        self,
        access_token: str,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
        sync_token: str | None = None,
        calendar_id: str = _PRIMARY_CALENDAR,
    ) -> CalendarEventsPage:
        """primary 캘린더 이벤트 조회. sync_token 있으면 증분, 없으면 [time_min, time_max] 전체.

        모든 페이지를 순회해 누적하고 마지막 응답의 nextSyncToken 을 반환한다.
        410 GONE(syncToken 만료) → CalendarSyncTokenExpiredError.
        """
        events: list[RawCalendarEvent] = []
        page_token: str | None = None
        next_sync_token: str | None = None
        url = _CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)

        for _ in range(_MAX_PAGES):
            params: dict[str, str | int] = {"maxResults": _PAGE_SIZE}
            if sync_token:
                params["syncToken"] = sync_token
            else:
                params["singleEvents"] = "true"
                params["showDeleted"] = "false"
                if time_min:
                    params["timeMin"] = time_min
                if time_max:
                    params["timeMax"] = time_max
            if page_token:
                params["pageToken"] = page_token

            response = await self._client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )

            if response.status_code == 410:
                raise CalendarSyncTokenExpiredError()
            if response.status_code == 401:
                raise CalendarReauthRequiredException("Calendar API returned 401.")
            if response.status_code >= 400:
                raise CalendarApiUnavailableException(
                    f"Calendar API returned {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            for item in data.get("items", []):
                parsed = _parse_event(item, calendar_id)
                if parsed is not None:
                    events.append(parsed)

            next_sync_token = data.get("nextSyncToken") or next_sync_token
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return CalendarEventsPage(events=events, next_sync_token=next_sync_token)
