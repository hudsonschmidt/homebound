from src import config
from sqlalchemy import create_engine

settings = config.get_settings()
connection_url = settings.DATABASE_URL

# Use synchronous engine for SQLite/PostgreSQL
if connection_url.startswith("sqlite"):
    # SQLite needs check_same_thread=False for FastAPI
    engine = create_engine(connection_url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
else:
    engine = create_engine(connection_url, pool_pre_ping=True)