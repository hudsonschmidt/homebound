# backend/app/core/db.py
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
import ssl
import certifi

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


# Supabase / PgBouncer-safe engine config
is_pooler = ":6543/" in settings.DATABASE_URL

connect_args: dict[str, Any] = {}
if is_pooler:
    connect_args["statement_cache_size"] = 0  # asyncpg: disable prepared stmt cache for PgBouncer

# Build a verified SSL context using certifi for Supabase hosts
if "supabase.com" in settings.DATABASE_URL or "supabase.co" in settings.DATABASE_URL:
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    ssl_ctx.check_hostname = True
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED
    connect_args["ssl"] = ssl_ctx  # asyncpg expects an SSLContext or True/False

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
