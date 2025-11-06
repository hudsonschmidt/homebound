from src import config
from sqlalchemy import create_engine

settings = config.get_settings()
connection_url = settings.DATABASE_URL

# Force psycopg2 (synchronous) driver
# Replace ANY async driver (asyncpg) with psycopg2
if "+asyncpg" in connection_url:
    connection_url = connection_url.replace("+asyncpg", "+psycopg2")
elif "postgresql+psycopg:" in connection_url:
    connection_url = connection_url.replace("postgresql+psycopg:", "postgresql+psycopg2:")
elif connection_url.startswith("postgres://"):
    connection_url = connection_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif connection_url.startswith("postgresql://"):
    connection_url = connection_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# Use synchronous engine for SQLite/PostgreSQL
if connection_url.startswith("sqlite"):
    # SQLite needs check_same_thread=False for FastAPI
    engine = create_engine(connection_url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
else:
    engine = create_engine(connection_url, pool_pre_ping=True)