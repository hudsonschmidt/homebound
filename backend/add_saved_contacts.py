#!/usr/bin/env python3
"""
Migration script to add saved_contacts JSON column to users table
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection URL
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")


async def add_saved_contacts_column():
    """Add saved_contacts column to users table"""
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Check if column already exists
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name = 'saved_contacts'
            )
        """)

        if exists:
            print("✓ Column 'saved_contacts' already exists in users table")
        else:
            # Add the saved_contacts column
            await conn.execute("""
                ALTER TABLE users
                ADD COLUMN saved_contacts JSONB DEFAULT '{}'::jsonb
            """)
            print("✓ Added 'saved_contacts' column to users table")

        # Verify the column was added
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name = 'saved_contacts'
        """)

        if columns:
            print(f"✓ Verified column: {columns[0]['column_name']} ({columns[0]['data_type']})")

        print("\n✅ Migration completed successfully!")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(add_saved_contacts_column())