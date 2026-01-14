import os
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv

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
    POSTGRES_URI: str = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URI") or "postgresql://myuser:mypassword@localhost:5432/mydatabase"

    # Development mode flag (must be defined before SECRET_KEY)
    DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() == "true"

    # JWT settings for authentication
    # SECURITY: In production (DEV_MODE=false), SECRET_KEY must be set via environment variable
    _secret_key_env: str | None = os.getenv("SECRET_KEY")
    if not DEV_MODE and not _secret_key_env:
        raise RuntimeError(
            "SECURITY ERROR: SECRET_KEY environment variable must be set in production. "
            "Set DEV_MODE=true for local development."
        )
    SECRET_KEY: str = _secret_key_env or "dev-secret-key-for-local-development-only"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days (balances security with mobile UX)
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

    # Push notification settings
    APNS_KEY_ID: str = os.getenv("APNS_KEY_ID", "")
    APNS_TEAM_ID: str = os.getenv("APNS_TEAM_ID", "")
    APNS_BUNDLE_ID: str = os.getenv("APNS_BUNDLE_ID", "com.homeboundapp.Homebound")
    APNS_AUTH_KEY_PATH: str = os.getenv("APNS_AUTH_KEY_PATH", "")
    APNS_PRIVATE_KEY: str = os.getenv("APNS_PRIVATE_KEY", "")  # For production (key contents)
    APNS_USE_SANDBOX: bool = os.getenv("APNS_USE_SANDBOX", "true").lower() == "true"

    def get_apns_private_key(self) -> str:
        """Load APNs private key from env var or file.

        Supports base64-encoded keys to avoid newline issues in env vars.
        """
        import base64

        # First check for direct key in environment (production)
        if self.APNS_PRIVATE_KEY:
            key = self.APNS_PRIVATE_KEY
            # Check if it's base64 encoded (doesn't start with -----)
            if not key.startswith("-----"):
                try:
                    key = base64.b64decode(key).decode("utf-8")
                except Exception:
                    pass  # Not base64, use as-is
            return key
        # Fall back to file path (local development)
        if self.APNS_AUTH_KEY_PATH and os.path.exists(self.APNS_AUTH_KEY_PATH):
            with open(self.APNS_AUTH_KEY_PATH) as f:
                return f.read()
        return ""

    # Apple Sign In settings
    APPLE_BUNDLE_ID: str = os.getenv("APPLE_BUNDLE_ID", "com.hudsonschmidt.Homebound")

    # Apple App Store Server API settings (for subscription validation)
    APP_STORE_KEY_ID: str = os.getenv("APP_STORE_KEY_ID", "")
    APP_STORE_ISSUER_ID: str = os.getenv("APP_STORE_ISSUER_ID", "")
    APP_STORE_PRIVATE_KEY: str = os.getenv("APP_STORE_PRIVATE_KEY", "")
    APP_BUNDLE_ID: str = os.getenv("APP_BUNDLE_ID", "com.hudsonschmidt.Homebound")

    # Development settings
    # DEV_MODE is defined earlier in the class for SECRET_KEY validation
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")

    # Notification backend settings
    EMAIL_BACKEND: str = os.getenv("EMAIL_BACKEND", "console")  # "resend" or "console"
    PUSH_BACKEND: str = os.getenv("PUSH_BACKEND", "dummy")  # "apns" or "dummy"


@lru_cache
def get_settings():
    return Settings()


# Create singleton instance for direct imports
settings = get_settings()
