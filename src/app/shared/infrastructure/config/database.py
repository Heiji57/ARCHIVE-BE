from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_", env_file=".env", extra="ignore")

    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
