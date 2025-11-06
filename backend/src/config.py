from dotenv import load_dotenv, find_dotenv
import os
from functools import lru_cache

# Load default first
load_dotenv(dotenv_path="default.env", override=False)

# Then override with .env if available
load_dotenv(dotenv_path=find_dotenv(".env"), override=True)


class Settings:
    # Database - use SQLite for local dev
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./homebound.db")

    # JWT settings for authentication
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days (for mobile persistent login)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90  # 90 days

    # Email settings for magic links
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@homeboundapp.com")

    # SMS settings for notifications
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # Push notification settings
    APNS_KEY_ID: str = os.getenv("APNS_KEY_ID", "")
    APNS_TEAM_ID: str = os.getenv("APNS_TEAM_ID", "")
    APNS_BUNDLE_ID: str = os.getenv("APNS_BUNDLE_ID", "com.homeboundapp.Homebound")
    APNS_AUTH_KEY_PATH: str = os.getenv("APNS_AUTH_KEY_PATH", "")

    # Development settings
    DEV_MODE: bool = os.getenv("DEV_MODE", "true").lower() == "true"
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")

    # Notification backend settings
    SMS_BACKEND: str = os.getenv("SMS_BACKEND", "dummy")  # "twilio" or "dummy"
    EMAIL_BACKEND: str = os.getenv("EMAIL_BACKEND", "console")  # "resend" or "console"
    PUSH_BACKEND: str = os.getenv("PUSH_BACKEND", "dummy")  # "apns" or "dummy"


@lru_cache()
def get_settings():
    return Settings()
