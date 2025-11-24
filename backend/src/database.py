from src import config
from sqlalchemy import create_engine

# Get connection URL from config
connection_url = config.get_settings().POSTGRES_URI

# Convert postgresql+psycopg:// to postgresql+psycopg2:// for compatibility
if "postgresql+psycopg:" in connection_url and "postgresql+psycopg2:" not in connection_url:
    connection_url = connection_url.replace("postgresql+psycopg:", "postgresql+psycopg2:")

# Add SSL mode for Supabase if not already present
if "supabase.com" in connection_url and "sslmode=" not in connection_url:
    separator = "&" if "?" in connection_url else "?"
    connection_url = f"{connection_url}{separator}sslmode=require"

# Create engine with connection pooling settings optimized for Supabase
# Session pooler supports multiple simultaneous connections
engine = create_engine(
    connection_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,  # Base pool size
    max_overflow=10,  # Allow up to 10 additional connections
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=False  # Set to True for SQL debugging
)
