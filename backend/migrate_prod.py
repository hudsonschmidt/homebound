#!/usr/bin/env python
"""
Production database migration script for Render
Run this once to fix the schema on Render's PostgreSQL
"""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def migrate_production():
    """Fix production database schema."""

    # Use Render's DATABASE_URL environment variable
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL environment variable not found!")
        return

    # Render provides postgresql:// but asyncpg needs postgresql+asyncpg://
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    elif database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+asyncpg://', 1)

    print(f"📦 Connecting to production database...")
    engine = create_async_engine(database_url, echo=True)

    async with engine.begin() as conn:
        try:
            # Check if user_id column exists in plans table
            result = await conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'plans'
                AND column_name = 'user_id'
            """))
            has_user_id = result.first() is not None

            if not has_user_id:
                print("❌ Missing user_id column in plans table. Fixing...")

                # Check if users table exists
                result = await conn.execute(text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'users'
                """))
                has_users_table = result.first() is not None

                if not has_users_table:
                    print("Creating users table...")
                    await conn.execute(text("""
                        CREATE TABLE users (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    print("✅ Created users table")

                # Create a default user
                result = await conn.execute(text("SELECT id FROM users LIMIT 1"))
                user = result.first()

                if not user:
                    await conn.execute(text(
                        "INSERT INTO users (email) VALUES (:email)"
                    ), {"email": "system@homeboundapp.com"})
                    result = await conn.execute(text("SELECT id FROM users WHERE email = :email"),
                                                {"email": "system@homeboundapp.com"})
                    user = result.first()

                default_user_id = user[0]

                # Add user_id column with default value
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

                print("✅ Added user_id column to plans table")
            else:
                print("✅ user_id column already exists in plans table")

            # Verify all tables exist
            for table in ['users', 'plans', 'contacts', 'events', 'devices', 'login_tokens']:
                result = await conn.execute(text(f"""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = '{table}'
                """))
                if result.first():
                    print(f"✅ Table '{table}' exists")
                else:
                    print(f"❌ Table '{table}' is missing!")

        except Exception as e:
            print(f"❌ Error during migration: {e}")
            raise

    await engine.dispose()
    print("✅ Production database migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_production())