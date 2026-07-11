from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=".env.local", extra="ignore")

    broker_url: str
    result_backend_url: str
    cache_url: str
    auth_url: str
