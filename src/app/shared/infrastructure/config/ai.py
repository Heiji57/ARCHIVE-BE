from pydantic_settings import BaseSettings, SettingsConfigDict


class AIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str
    gemini_model: str = "gemini-2.5-flash"
