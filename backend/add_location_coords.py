#!/usr/bin/env python3
"""
Migration script to add location coordinate columns to the plans table.
This adds location_lat and location_lng columns to store geographic coordinates
for trip locations, enabling future location-based features and statistics.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Convert to async URL if needed
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://")


async def add_location_columns():
    """Add location_lat and location_lng columns to plans table."""

    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        print("Adding location coordinate columns to plans table...")

        # Check if columns already exist
        check_query = text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'plans'
            AND column_name IN ('location_lat', 'location_lng')
        """)

        result = await conn.execute(check_query)
        existing_columns = [row[0] for row in result]

        if 'location_lat' in existing_columns and 'location_lng' in existing_columns:
            print("Location columns already exist in plans table")
            return

        # Add location_lat column if it doesn't exist
        if 'location_lat' not in existing_columns:
            await conn.execute(text("""
                ALTER TABLE plans
                ADD COLUMN location_lat DOUBLE PRECISION DEFAULT NULL
            """))
            print("Added location_lat column to plans table")

        # Add location_lng column if it doesn't exist
        if 'location_lng' not in existing_columns:
            await conn.execute(text("""
                ALTER TABLE plans
                ADD COLUMN location_lng DOUBLE PRECISION DEFAULT NULL
            """))
            print("Added location_lng column to plans table")

        # Verify columns were added
        verify_query = text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'plans'
            AND column_name IN ('location_lat', 'location_lng')
            ORDER BY column_name
        """)

        result = await conn.execute(verify_query)
        columns = result.fetchall()

        print("\nVerification - New columns in plans table:")
        for col_name, data_type, nullable in columns:
            print(f"  - {col_name}: {data_type} (nullable: {nullable})")

        print("\nMigration completed successfully!")
        print("Plans can now store location coordinates for future location-based features.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_location_columns())