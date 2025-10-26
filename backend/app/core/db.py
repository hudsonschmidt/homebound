# backend/app/core/db.py
from __future__ import annotations

import os
import ssl
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


# ---- Supabase / PgBouncer-safe engine config ----
is_pooler = ":6543/" in settings.DATABASE_URL

connect_args: dict[str, Any] = {}
if is_pooler:
    # asyncpg: disable prepared statement cache (PgBouncer-friendly)
    connect_args["statement_cache_size"] = 0

host = urlparse(settings.DATABASE_URL).hostname or ""

# STAGING UNBLOCK:
# If connecting to Supabase, default to *insecure TLS* unless explicitly turned off.
# This avoids the current "self-signed certificate in certificate chain" failure.
force_insecure = os.getenv("PG_SSL_INSECURE", "true").lower() == "true"
if "supabase.com" in host or "supabase.co" in host:
    ssl_ctx = ssl.create_default_context()
    if force_insecure:
        ssl_ctx.check_hostname = False
        ssl_ctx.verif_
