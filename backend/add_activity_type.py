#!/usr/bin/env python
"""
Add activity_type column to plans table
"""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def add_activity_type_column():
    """Add activity_type column to plans table."""

    database_url = settings.DATABASE_URL

    # Handle different database URLs for production
    if 'DATABASE_URL' in os.environ:
        database_url = os.environ['DATABASE_URL']
        if database_url.startswith('postgresql://'):
            database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        elif database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql+asyncpg://', 1)

    engine = create_async_engine(database_url, echo=True)

    async with engine.begin() as conn:
        try:
            # Check if activity_type column exists
            if 'postgresql' in database_url:
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'plans'
                    AND column_name = 'activity_type'
                """))
                has_column = result.first() is not None
            else:
                # SQLite
                result = await conn.execute(text("PRAGMA table_info(plans)"))
                columns = result.fetchall()
                has_column = any(col[1] == 'activity_type' for col in columns)

            if not has_column:
                print("Adding activity_type column to plans table...")

                # Add the column with default value
                await conn.execute(text("""
                    ALTER TABLE plans
                    ADD COLUMN activity_type VARCHAR(50) DEFAULT 'other' NOT NULL
                """))

                print("✅ Added activity_type column to plans table")
            else:
                print("✅ activity_type column already exists in plans table")

        except Exception as e:
            print(f"❌ Error: {e}")
            raise

    await engine.dispose()
    print("✅ Migration complete!")

if __name__ == "__main__":
    asyncio.run(add_activity_type_column())