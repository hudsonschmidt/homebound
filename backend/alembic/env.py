import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# Load .env file
load_dotenv()

# Alembic Config object
config = context.config

# Load DB URI from environment and override config
# Check DATABASE_URL first (Render sets this), then POSTGRES_URI, then default to local SQLite
_db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URI")
database_url: str = _db_url if _db_url else "sqlite:///./homebound.db"

# Debug: Print original URL (remove credentials for security)
if '@' in database_url:
    scheme = database_url.split('@')[0].split('://')[0]
    host = database_url.split('@')[1]
    url_for_display = f"{scheme}://***@{host}"
else:
    url_for_display = database_url
print(f"[Alembic] DATABASE_URL: {url_for_display}")

# Only apply PostgreSQL-specific transformations if using PostgreSQL
if database_url.startswith("postgresql") or database_url.startswith("postgres://"):
    # Force psycopg2 (synchronous) driver for Alembic migrations
    # Replace ANY async driver (asyncpg) with psycopg2
    if "+asyncpg" in database_url:
        database_url = database_url.replace("+asyncpg", "+psycopg2")
    elif "postgresql+psycopg:" in database_url:
        database_url = database_url.replace("postgresql+psycopg:", "postgresql+psycopg2:")
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    # CRITICAL: Switch Supabase from Session Mode (port 5432) to Transaction Mode (port 6543)
    if "supabase.com" in database_url and ":5432" in database_url:
        print("[Alembic] ⚠️  Supabase Session Mode detected (port 5432)")
        print("[Alembic] Switching to Transaction Mode (port 6543)")
        database_url = database_url.replace(":5432", ":6543")

    # Add SSL mode for Supabase connection pooler if not already present
    if "supabase.com" in database_url and "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    print(f"[Alembic] Using PostgreSQL: {database_url.split('://')[0]}")
else:
    print(f"[Alembic] Using SQLite database")

config.set_main_option("sqlalchemy.url", database_url)

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your metadata (for `--autogenerate`)
# from app.db import Base
target_metadata = None  # or Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    if not configuration:
        raise Exception("No config section for Alembic")
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


# Entry point
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
