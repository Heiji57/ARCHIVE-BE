from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    pre_auth_token_expire_minutes: int = 5

    # Email verification
    email_verify_code_ttl_seconds: int = 600    # 인증 코드 유효 시간 (10분)
    email_verified_ttl_seconds: int = 1800      # 인증 완료 상태 유지 (30분)
    email_cooldown_ttl_seconds: int = 60        # 재발송 대기
    email_max_verify_attempts: int = 5
