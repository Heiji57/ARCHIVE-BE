from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ai import AIConfig
from .auth import AuthConfig
from .database import DatabaseConfig
from .email import EmailConfig
from .oauth import GitHubOAuthConfig, GoogleCalendarConfig, GoogleOAuthConfig
from .redis import RedisConfig
from .retrospective import RetrospectiveConfig
from .storage import StorageConfig
from .topic import TopicConfig


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    cors_origins: list[str] = Field(default_factory=list)
    frontend_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"

    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    github_oauth: GitHubOAuthConfig = Field(default_factory=GitHubOAuthConfig)
    google_oauth: GoogleOAuthConfig = Field(default_factory=GoogleOAuthConfig)
    google_calendar: GoogleCalendarConfig = Field(default_factory=GoogleCalendarConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    retrospective: RetrospectiveConfig = Field(default_factory=RetrospectiveConfig)
    topic: TopicConfig = Field(default_factory=TopicConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @model_validator(mode="after")
    def _production_needs_object_storage(self) -> Self:
        # 운영 compose 는 컨테이너마다 볼륨이 없다 — 로컬 파일이면 워커가 만든 zip 을 API 가
        # 못 보고 재배포 때 사진이 사라진다. 조용히 깨지지 않게 시작할 때 막는다.
        if self.is_production and self.storage.backend != "s3":
            raise ValueError("APP_ENV=production needs STORAGE_BACKEND=s3")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> AppConfig:
    return AppConfig()
