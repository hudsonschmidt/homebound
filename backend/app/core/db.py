# backend/app/core/db.py
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 2.x Declarative base for all models."""
    pass


# ---- Supabase / PgBouncer-safe engine config ----
# - Port 6543 = Session Pooler. Disable asyncpg statement cache.
# - pool_pre_ping=True: drop/reconnect stale connections automatically.
# - pool_recycle: proactively recycle connections to avoid timeouts.
# - Explicit SSL for asyncpg when using Supabase.
is_pooler = ":6543/" in settings.DATABASE_URL

connect_args: dict[str, Any] = {}
if is_pooler:
    connect_args["statement_cache_size"] = 0

# Force TLS for Supabase hosts (asyncpg uses `ssl`, not `sslmode`)
if "supabase.com" in settings.DATABASE_URL or "supabase.co" in settings.DATABASE_URL:
    # If URL already has ?ssl=true, passing this again is harmless.
    connect_args.setdefault("ssl", True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,   # seconds
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
