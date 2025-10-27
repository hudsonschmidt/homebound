#!/usr/bin/env python3
"""
Add missing columns to production database
"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

async def add_missing_columns():
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found in environment")
        return

    # Create engine
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check and add missing columns to plans table
        print("Adding missing columns to plans table...")

        # Add completed_at column if it doesn't exist
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='plans' AND column_name='completed_at'
                ) THEN
                    ALTER TABLE plans ADD COLUMN completed_at TIMESTAMP;
                END IF;
            END $$;
        """))

        # Add extended_count column if it doesn't exist
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='plans' AND column_name='extended_count'
                ) THEN
                    ALTER TABLE plans ADD COLUMN extended_count INTEGER DEFAULT 0;
                END IF;
            END $$;
        """))

        # Add last_checkin_at column if it doesn't exist
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='plans' AND column_name='last_checkin_at'
                ) THEN
                    ALTER TABLE plans ADD COLUMN last_checkin_at TIMESTAMP;
                END IF;
            END $$;
        """))

        # Add missing columns to users table
        print("Adding missing columns to users table...")

        # Add name column if it doesn't exist
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='name'
                ) THEN
                    ALTER TABLE users ADD COLUMN name VARCHAR(100);
                END IF;
            END $$;
        """))

        # Add age column if it doesn't exist
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='age'
                ) THEN
                    ALTER TABLE users ADD COLUMN age INTEGER;
                END IF;
            END $$;
        """))

        print("All missing columns added successfully!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(add_missing_columns())