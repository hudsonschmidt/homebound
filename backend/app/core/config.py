from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "dev"
    SECRET_KEY: str = "dev_change_me"
    TIMEZONE: str = "UTC"
    DATABASE_URL: str = "sqlite+aiosqlite:///./homebound.db"

    EMAIL_BACKEND: str = "console"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMS_BACKEND: str = "dummy"

    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(env_file="backend/.env", env_file_encoding="utf-8")


settings = Settings()
