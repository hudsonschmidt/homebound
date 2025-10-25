from __future__ import annotations

import json
import os
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv_or_json(value: str | None, default: List[str]) -> List[str]:
    if value is None or value.strip() == "":
        return default
    s = value.strip()
    if s.startswith("["):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [str(x) for x in arr]
        except Exception:
            pass
    return [item.strip() for item in s.split(",") if item.strip()]


class Settings(BaseSettings):
    # App
    APP_ENV: str = "dev"
    SECRET_KEY: str = "dev_change_me"
    TIMEZONE: str = "UTC"
    DATABASE_URL: str = "sqlite+aiosqlite:///./homebound.db"

    # Messaging (dev-safe)
    EMAIL_BACKEND: str = "console"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMS_BACKEND: str = "dummy"

    # Public base for links
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    JWT_ACCESS_EXPIRES_SECONDS: int = 3600
    JWT_REFRESH_EXPIRES_SECONDS: int = 2592000  # 30 days

    # iOS / Universal Links
    IOS_TEAM_ID: str = "YOUR_TEAM_ID"
    IOS_BUNDLE_ID: str = "com.example.homebound"
    UNIVERSAL_LINK_PATHS: str = "/t/*"  # CSV or JSON array

    # CORS
    CORS_ALLOW_ORIGINS: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://127.0.0.1:8000"
    )

    # Push / APNs
    PUSH_BACKEND: str = "dummy"  # 'dummy' | 'apns'
    APNS_USE_SANDBOX: bool = True
    APNS_KEY_ID: str = ""  # e.g., ABC123XYZ
    APNS_PRIVATE_KEY_PATH: str = ""  # path to .p8 (preferred)
    APNS_PRIVATE_KEY: str = ""  # or inline full .p8 contents

    model_config = SettingsConfigDict(env_file="backend/.env", env_file_encoding="utf-8")

    # ---- Derived list properties ----
    @property
    def UNIVERSAL_LINK_PATHS_LIST(self) -> List[str]:
        return _parse_csv_or_json(self.UNIVERSAL_LINK_PATHS, default=["/t/*"])

    @property
    def CORS_ALLOW_ORIGINS_LIST(self) -> List[str]:
        return _parse_csv_or_json(
            self.CORS_ALLOW_ORIGINS,
            default=[
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
            ],
        )

    # ---- APNs helpers ----
    def get_apns_private_key(self) -> str:
        if self.APNS_PRIVATE_KEY_PATH and os.path.exists(self.APNS_PRIVATE_KEY_PATH):
            with open(self.APNS_PRIVATE_KEY_PATH, "r", encoding="utf-8") as f:
                return f.read()
        return self.APNS_PRIVATE_KEY


settings = Settings()
