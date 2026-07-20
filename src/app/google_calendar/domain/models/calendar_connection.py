from dataclasses import dataclass
from datetime import datetime, timedelta

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class GoogleCalendarConnection(BaseEntity):
    """사용자의 Google Calendar 연결 (1 user : 1 connection).

    refresh_token 으로 access_token 을 주기적으로 갱신한다 — 백그라운드 AI 요약
    시점(현지 1am)에도 유효한 토큰을 확보하기 위함. `needs_reauth` 가 True 면
    refresh 가 실패(revoke 등)한 상태로, FE 가 재연결을 유도한다.

    `sync_token` 은 Google Calendar 증분 동기화 토큰 — 다음 sync 시 변경분만 받는다.
    """
    user_id: str
    google_user_id: str
    access_token: str
    refresh_token: str
    token_expires_at: datetime
    scope: str
    sync_token: str | None = None
    last_synced_at: datetime | None = None
    # 사용자가 실제로 캘린더 데이터를 조회한 마지막 시각(요청 경로에서만 갱신).
    # 백그라운드 주기 sync 가 "최근 활성 사용자"만 동기화하도록 거르는 기준.
    # last_synced_at 은 sync 자체가 갱신하므로 활성도 신호로 쓸 수 없다(순환).
    last_active_at: datetime | None = None
    needs_reauth: bool = False

    def is_token_expired(self, now: datetime, skew_seconds: int = 60) -> bool:
        """access_token 만료 여부 (skew 만큼 보수적으로 앞당겨 판정)."""
        return now >= self.token_expires_at - timedelta(seconds=skew_seconds)

    def apply_refreshed_token(
        self, access_token: str, expires_in_seconds: int, now: datetime
    ) -> None:
        self.access_token = access_token
        self.token_expires_at = now + timedelta(seconds=expires_in_seconds)
        self.needs_reauth = False
        self.updated_at = now
