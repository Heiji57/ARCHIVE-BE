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
