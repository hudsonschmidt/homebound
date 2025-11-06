from src import config
from sqlalchemy import create_engine

settings = config.get_settings()
connection_url = settings.DATABASE_URL

# Render uses postgres:// but SQLAlchemy needs postgresql://
if connection_url.startswith("postgres://"):
    connection_url = connection_url.replace("postgres://", "postgresql://", 1)

# Use synchronous engine for SQLite/PostgreSQL
if connection_url.startswith("sqlite"):
    # SQLite needs check_same_thread=False for FastAPI
    engine = create_engine(connection_url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
else:
    engine = create_engine(connection_url, pool_pre_ping=True)