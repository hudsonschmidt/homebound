#!/usr/bin/env python3
"""
Script to update activity types in the database
"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

# All activity types from iOS app
ACTIVITY_TYPES = [
    'hiking',
    'biking',
    'running',
    'climbing',
    'camping',
    'backpacking',
    'skiing',
    'snowboarding',
    'kayaking',
    'sailing',
    'fishing',
    'surfing',
    'scuba_diving',
    'free_diving',
    'snorkeling',
    'horseback_riding',
    'driving',
    'flying',
    'other'
]

async def update_activity_types():
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found in environment")
        return

    # Create engine
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        print("Checking activity_type column...")

        # Check if activity_type column exists
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'plans'
            AND column_name = 'activity_type'
        """))

        if not result.first():
            print("Adding activity_type column to plans table...")
            await conn.execute(text("""
                ALTER TABLE plans
                ADD COLUMN activity_type VARCHAR(50) DEFAULT 'other' NOT NULL
            """))
            print("✅ Added activity_type column")
        else:
            print("✅ activity_type column already exists")

        # Update any constraint if needed
        print("\nUpdating activity_type constraint...")

        # Drop existing constraint if it exists
        try:
            await conn.execute(text("""
                ALTER TABLE plans
                DROP CONSTRAINT IF EXISTS plans_activity_type_check;
            """))
        except:
            pass  # Constraint might not exist

        # Create new constraint with all activity types
        activity_types_sql = ', '.join(f"'{t}'" for t in ACTIVITY_TYPES)
        await conn.execute(text(f"""
            ALTER TABLE plans
            ADD CONSTRAINT plans_activity_type_check
            CHECK (activity_type IN ({activity_types_sql}));
        """))

        print(f"✅ Successfully updated activity_type constraint with {len(ACTIVITY_TYPES)} types")
        print(f"Activity types: {', '.join(ACTIVITY_TYPES)}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_activity_types())