# app/core/db.py
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ---- One source of truth for the URL ----
DB_URL = os.getenv("ASYNC_DATABASE_URL")  # e.g., postgresql+asyncpg://...:6543/db?sslmode=require
if not DB_URL:
    # fall back if you keep one in your settings module
    from .config import settings
    DB_URL = settings.DATABASE_URL

if not DB_URL:
    raise RuntimeError("ASYNC_DATABASE_URL (or settings.DATABASE_URL) must be set")

# Ensure we have the async driver and SSL required
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)
if "+asyncpg" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
if "sslmode=" not in DB_URL:
    DB_URL += ("&" if "?" in DB_URL else "?") + "sslmode=require"

# Detect PgBouncer (Supabase pooler) by the pooled port
is_pooler = ":6543/" in DB_URL

# ---- asyncpg / PgBouncer-safe connect args ----
connect_args: dict[str, Any] = {}
# Disable prepared statements cache in asyncpg when behind PgBouncer txn/statement mode
# (prevents DuplicatePreparedStatementError)
connect_args["statement_cache_size"] = 0 if is_pooler else 0  # safe to keep 0 always

# ---- Engine ----
engine = create_async_engine(
    DB_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "1")),   # keep tiny on serverless
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "0")),
    pool_recycle=1800,
    pool_timeout=30,
    connect_args=connect_args,                       # ← use the dict we built
)

# Single session factory
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

__all__ = ("Base", "engine", "AsyncSessionLocal", "get_session")
