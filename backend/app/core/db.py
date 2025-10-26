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

host = (urlparse(settings.DATABASE_URL).hostname or "").lower()

# STAGING UNBLOCK:
# For Supabase, default to *insecure TLS* unless explicitly turned off.
# Set PG_SSL_INSECURE=false later once you add a proper CA bundle.
force_insecure = os.getenv("PG_SSL_INSECURE", "true").lower() == "true"
if "supabase.com" in host or "supabase.co" in host:
    ssl_ctx = ssl.create_default_context()
    if force_insecure:
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
    else:
        # When ready for strict TLS, load a real CA bundle here:
        # ssl_ctx.load_verify_locations("backend/certs/rds-ca.pem")
        ssl_ctx.check_hostname = True
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
    connect_args["ssl"] = ssl_ctx

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,  # seconds
    pool_size=5,
    max_overflow=5,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


__all__ = ("Base", "engine", "SessionLocal", "get_session")
