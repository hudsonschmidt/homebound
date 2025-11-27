from dotenv import load_dotenv, find_dotenv
import os
from functools import lru_cache

# Load .env files for local development
# IMPORTANT: override=False means environment variables (set in Render) take precedence
# This ensures production environment variables aren't overridden by local .env files
load_dotenv(dotenv_path="default.env", override=False)
load_dotenv(dotenv_path=find_dotenv(".env"), override=False)  # Changed to False!


class Settings:
    # Database - Docker PostgreSQL for local dev, Supabase connection pooler for production
    # Check DATABASE_URL first (Render sets this), then POSTGRES_URI, then default to local Docker
    # For Supabase: Use session pooler connection string from Supabase dashboard
    # Example: postgresql+psycopg://postgres.[ref]:[password]@aws-1-us-east-2.pooler.supabase.com:5432/postgres
    POSTGRES_URI: str = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URI", "postgresql://myuser:mypassword@localhost:5432/mydatabase")

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

    # Resend email settings
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "noreply@homeboundapp.com")
    RESEND_ALERTS_EMAIL: str = os.getenv("RESEND_ALERTS_EMAIL", "alerts@homeboundapp.com")
    RESEND_HELLO_EMAIL: str = os.getenv("RESEND_HELLO_EMAIL", "hello@homeboundapp.com")
    RESEND_UPDATE_EMAIL: str = os.getenv("RESEND_UPDATE_EMAIL", "update@homeboundapp.com")

    # SMS settings for notifications
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")
    TWILIO_MESSAGING_SERVICE_SID: str = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "")

    # Push notification settings
    APNS_KEY_ID: str = os.getenv("APNS_KEY_ID", "")
    APNS_TEAM_ID: str = os.getenv("APNS_TEAM_ID", "")
    APNS_BUNDLE_ID: str = os.getenv("APNS_BUNDLE_ID", "com.homeboundapp.Homebound")
    APNS_AUTH_KEY_PATH: str = os.getenv("APNS_AUTH_KEY_PATH", "")

    # Apple Sign In settings
    APPLE_BUNDLE_ID: str = os.getenv("APPLE_BUNDLE_ID", "com.hudsonschmidt.Homebound")

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


# Create singleton instance for direct imports
settings = get_settings()
