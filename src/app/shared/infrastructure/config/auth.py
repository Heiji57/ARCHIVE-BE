from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Email verification
    email_verify_code_ttl_seconds: int = 600    # 인증 코드 유효 시간 (10분)
    email_verified_ttl_seconds: int = 1800      # 인증 완료 상태 유지 (30분)
    email_cooldown_ttl_seconds: int = 60        # 재발송 대기
    email_max_verify_attempts: int = 5

    # OAuth flows
    oauth_state_ttl_seconds: int = 600          # OAuth state 1회용 토큰 만료 (10분)
    onboarding_token_ttl_seconds: int = 1800    # OAuth 신규 사용자 온보딩 토큰 만료 (30분)

    # Password reset
    password_reset_ttl_seconds: int = 1800              # 비밀번호 재설정 토큰 만료 (30분)
    password_reset_cooldown_ttl_seconds: int = 60       # 재설정 메일 재발송 쿨다운

    # Login brute-force 방어 (Redis 고정 윈도우, email+IP 키)
    login_max_attempts: int = 10                # window 안 허용 실패 횟수
    login_attempt_window_seconds: int = 900     # 실패 카운터 윈도우(15분)

    # Session security
    session_grace_window_seconds: float = 5.0   # 동시 refresh race 흡수 윈도
