#!/usr/bin/env python
"""
Fix database schema - This script will check and fix the database schema issues
"""
import asyncio
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def check_and_fix_schema():
    """Check and fix missing columns in the database."""

    # Create engine
    engine = create_async_engine(settings.DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        try:
            # Check if user_id column exists in plans table
            if 'postgresql' in settings.DATABASE_URL:
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'plans'
                    AND column_name = 'user_id'
                """))
                has_user_id = result.first() is not None
            else:
                # SQLite
                result = await conn.execute(text("PRAGMA table_info(plans)"))
                columns = result.fetchall()
                has_user_id = any(col[1] == 'user_id' for col in columns)

            if not has_user_id:
                print("❌ Missing user_id column in plans table")

                # Check if users table exists
                if 'postgresql' in settings.DATABASE_URL:
                    result = await conn.execute(text("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_name = 'users'
                    """))
                    has_users_table = result.first() is not None
                else:
                    result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"))
                    has_users_table = result.first() is not None

                if not has_users_table:
                    print("❌ Users table doesn't exist. Creating it first...")

                    # Create users table
                    await conn.execute(text("""
                        CREATE TABLE users (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """ if 'postgresql' in settings.DATABASE_URL else """
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    print("✅ Created users table")

                # Now add user_id column to plans table
                print("Adding user_id column to plans table...")

                # First, create a default user if none exists
                result = await conn.execute(text("SELECT id FROM users LIMIT 1"))
                user = result.first()

                if not user:
                    await conn.execute(text(
                        "INSERT INTO users (email) VALUES (:email)"
                    ), {"email": "default@homeboundapp.com"})
                    result = await conn.execute(text("SELECT id FROM users WHERE email = :email"),
                                                {"email": "default@homeboundapp.com"})
                    user = result.first()

                default_user_id = user[0]

                # Add the column with a default value
                if 'postgresql' in settings.DATABASE_URL:
                    await conn.execute(text(f"""
                        ALTER TABLE plans
                        ADD COLUMN user_id INTEGER DEFAULT {default_user_id} NOT NULL
                    """))
                    # Add foreign key constraint
                    await conn.execute(text("""
                        ALTER TABLE plans
                        ADD CONSTRAINT fk_plans_user_id
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    """))
                else:
                    # SQLite doesn't support adding columns with foreign keys easily
                    # We'll need to recreate the table
                    print("SQLite detected - this would require table recreation")
                    # For now, just add the column
                    await conn.execute(text(f"""
                        ALTER TABLE plans
                        ADD COLUMN user_id INTEGER DEFAULT {default_user_id} NOT NULL
                    """))

                print("✅ Added user_id column to plans table")
            else:
                print("✅ user_id column already exists in plans table")

        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

    await engine.dispose()
    print("✅ Database schema check complete!")

if __name__ == "__main__":
    asyncio.run(check_and_fix_schema())