from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ai import AIConfig
from .auth import AuthConfig
from .database import DatabaseConfig
from .email import EmailConfig
from .oauth import GitHubOAuthConfig, GoogleOAuthConfig
from .redis import RedisConfig


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: list[str] = Field(default_factory=list)

    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    github_oauth: GitHubOAuthConfig = Field(default_factory=GitHubOAuthConfig)
    google_oauth: GoogleOAuthConfig = Field(default_factory=GoogleOAuthConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> AppConfig:
    return AppConfig()
