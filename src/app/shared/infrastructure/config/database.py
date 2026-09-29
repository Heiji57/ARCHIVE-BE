from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_", env_file=".env", extra="ignore")

    url: str
    # SQL echo 는 파라미터까지 로그에 남길 수 있어(OAuth 토큰 등) 기본 off — 명시적 opt-in.
    # 켜더라도 엔진 생성 시 hide_parameters=True 로 값은 가린다.
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
