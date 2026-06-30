from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubOAuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GITHUB_", env_file=".env", extra="ignore")

    client_id: str
    client_secret: str
    redirect_uri: str


class GoogleOAuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOOGLE_", env_file=".env", extra="ignore")

    client_id: str
    client_secret: str
    redirect_uri: str


class GoogleCalendarConfig(BaseSettings):
    """Google Calendar 연동 설정.

    로그인용 Google OAuth(`GoogleOAuthConfig`)와 client_id/secret 은 공유하되
    (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`), 캘린더 전용 redirect_uri·scope·
    동기화 파라미터는 별도로 관리한다.

    캘린더는 access_token(1h 만료)만으로는 백그라운드 AI 요약 시점에 토큰이
    만료되므로 `access_type=offline` 으로 refresh_token 을 발급받아 저장한다.
    """
    model_config = SettingsConfigDict(env_prefix="GOOGLE_", env_file=".env", extra="ignore")

    client_id: str
    client_secret: str
    # 캘린더 콜백은 일반 OAuth 와 분리 — FE proxy origin 으로 통일 (callback HTML postMessage).
    calendar_redirect_uri: str = "http://localhost:5173/api/v1/calendar/callback"
    # openid email 은 google_user_id 확보용, calendar.readonly 는 이벤트 조회용.
    calendar_scope: str = (
        "openid email https://www.googleapis.com/auth/calendar.readonly"
    )
    # GET /todos 온디맨드 sync 임계 — 마지막 sync 후 이 시간 지나면 증분 재동기화.
    # 백그라운드 주기 sync 가 최신성을 책임지므로, 온디맨드는 "앱을 막 열었을 때
    # 즉시 반영" 보조 역할만 한다. 짧게 잡아 첫 진입 시 빠르게 반영.
    calendar_sync_staleness_seconds: int = 120
    # 초기 full sync 윈도우(과거 일수). annual 요약 커버를 위해 ~13개월.
    calendar_initial_window_days: int = 400
    # 미래 이벤트 조회 윈도우(앞으로 일수) — 다가오는 일정도 todo 뷰에 표시.
    calendar_future_window_days: int = 90
    # 캘린더 연결 OAuth state TTL(초).
    calendar_state_ttl_seconds: int = 600
