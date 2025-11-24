from src import config
from sqlalchemy import create_engine

# Get connection URL from config
connection_url = config.get_settings().POSTGRES_URI

# Convert postgresql+psycopg:// to postgresql+psycopg2:// for compatibility
if "postgresql+psycopg:" in connection_url and "postgresql+psycopg2:" not in connection_url:
    connection_url = connection_url.replace("postgresql+psycopg:", "postgresql+psycopg2:")

# CRITICAL: Switch Supabase from Session Mode (port 5432) to Transaction Mode (port 6543)
# Transaction mode supports many more concurrent connections and is recommended for web apps
# Session mode has very low connection limits and causes "MaxClientsInSessionMode" errors
if "supabase.com" in connection_url and ":5432" in connection_url:
    print("[Database] ⚠️  Supabase Session Mode detected (port 5432) - switching to Transaction Mode (port 6543)")
    connection_url = connection_url.replace(":5432", ":6543")

# Add SSL mode for Supabase if not already present
if "supabase.com" in connection_url and "sslmode=" not in connection_url:
    separator = "&" if "?" in connection_url else "?"
    connection_url = f"{connection_url}{separator}sslmode=require"

# Create engine with connection pooling settings optimized for Supabase Transaction Mode
# Transaction mode can handle many more concurrent connections via multiplexing
engine = create_engine(
    connection_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=3,  # Reduced base pool size for better connection management
    max_overflow=7,  # Allow up to 7 additional connections (10 total max)
    pool_recycle=300,  # Recycle connections after 5 minutes (Transaction mode preference)
    echo=False  # Set to True for SQL debugging
)

print(f"[Database] ✅ SQLAlchemy engine created with pool_size=3, max_overflow=7")
