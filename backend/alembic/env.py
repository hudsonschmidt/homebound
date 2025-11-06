from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config object
config = context.config

# Load DB URI from environment and override config
database_url = os.getenv("DATABASE_URL", "sqlite:///./homebound.db")

# Debug: Print original URL (remove credentials for security)
url_for_display = database_url.split('@')[0].split('://')[0] + '://***@' + database_url.split('@')[1] if '@' in database_url else database_url
print(f"[Alembic] Original DATABASE_URL scheme: {url_for_display.split('://')[0]}")

# Render uses postgres:// but SQLAlchemy needs postgresql://
# Also ensure we use psycopg2 (synchronous) not asyncpg for Alembic
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif database_url.startswith("postgresql://") and "+psycopg" not in database_url:
    # If it's already postgresql:// but doesn't specify a driver, add psycopg2
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
elif "postgresql" in database_url and "+psycopg2" not in database_url and "+asyncpg" not in database_url:
    # Catch any other postgresql URLs and force psycopg2
    database_url = database_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

print(f"[Alembic] Final URL scheme: {database_url.split('://')[0]}")

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
