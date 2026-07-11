from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMTP_", env_file=".env", extra="ignore")

    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    from_email: str = ""
    use_tls: bool = True
