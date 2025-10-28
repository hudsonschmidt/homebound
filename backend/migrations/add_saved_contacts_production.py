#!/usr/bin/env python3
"""
Production migration script to add saved_contacts column to users table.
This script is designed to be run on the production PostgreSQL database.

To run this script on production:
1. Set the DATABASE_URL environment variable to your production database URL
2. Run: python add_saved_contacts_production.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def add_saved_contacts_column():
    """Add saved_contacts column to users table in production."""

    # Get database URL from environment
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Please set it to your production database URL")
        return False

    # Convert to async URL if needed
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://")

    print(f"Connecting to database...")
    print(f"URL prefix: {DATABASE_URL[:30]}...")  # Show only the beginning for security

    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=True)

    try:
        async with engine.begin() as conn:
            print("\nChecking if saved_contacts column already exists...")

            # Check if column already exists
            check_query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name = 'saved_contacts'
            """)

            result = await conn.execute(check_query)
            existing = result.fetchone()

            if existing:
                print("✓ Column 'saved_contacts' already exists in users table")
                return True

            print("Adding saved_contacts column to users table...")

            # Add the column
            alter_query = text("""
                ALTER TABLE users
                ADD COLUMN saved_contacts JSON DEFAULT '{}'::json
            """)

            await conn.execute(alter_query)
            print("✓ Successfully added saved_contacts column")

            # Verify the column was added
            verify_query = text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name = 'saved_contacts'
            """)

            result = await conn.execute(verify_query)
            column = result.fetchone()

            if column:
                print(f"\nColumn details:")
                print(f"  Name: {column[0]}")
                print(f"  Type: {column[1]}")
                print(f"  Nullable: {column[2]}")
                print(f"  Default: {column[3]}")
                print("\n✅ Migration completed successfully!")
                return True
            else:
                print("\n❌ Column was not created successfully")
                return False

    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        return False
    finally:
        await engine.dispose()


async def main():
    """Main function to run the migration."""
    print("=" * 60)
    print("PRODUCTION DATABASE MIGRATION")
    print("Adding saved_contacts column to users table")
    print("=" * 60)

    # Safety check
    response = input("\n⚠️  This will modify the PRODUCTION database. Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        return

    success = await add_saved_contacts_column()

    if success:
        print("\n✅ Migration completed successfully!")
        print("The saved_contacts column has been added to the users table.")
    else:
        print("\n❌ Migration failed or was not needed.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())