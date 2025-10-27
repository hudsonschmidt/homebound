#!/usr/bin/env python3
"""
PostgreSQL migration script to add new fields for enhanced plan features.
Run this to update the PostgreSQL database with new columns.
"""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/homebound")

async def run_migration():
    """Add new columns to PostgreSQL database."""
    engine = create_async_engine(DATABASE_URL)

    migrations = [
        # Plans table migrations
        "ALTER TABLE plans ADD COLUMN IF NOT EXISTS activity_type VARCHAR(50) DEFAULT 'other'",
        "ALTER TABLE plans ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
        "ALTER TABLE plans ADD COLUMN IF NOT EXISTS extended_count INTEGER DEFAULT 0",
        "ALTER TABLE plans ADD COLUMN IF NOT EXISTS last_checkin_at TIMESTAMP",

        # Users table migrations
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(32)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true",

        # Devices table migrations
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS env VARCHAR(16) DEFAULT 'sandbox'",
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]

    async with engine.begin() as conn:
        for migration in migrations:
            try:
                await conn.execute(text(migration))
                print(f"✅ Applied: {migration[:50]}...")
            except Exception as e:
                print(f"⚠️  Skipped (may already exist): {migration[:50]}... - {str(e)[:50]}")

    await engine.dispose()
    print("\n✅ PostgreSQL migration complete!")

if __name__ == "__main__":
    asyncio.run(run_migration())