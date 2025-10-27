#!/usr/bin/env python3
"""
Database migration script to add new fields for enhanced plan features.
Run this to update existing database with new columns.
"""
import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = Path("homebound.db")

def run_migration():
    """Add new columns to support enhanced plan features."""
    if not DB_PATH.exists():
        print(f"❌ Database {DB_PATH} not found")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if migration already applied
        cursor.execute("PRAGMA table_info(plans)")
        columns = [col[1] for col in cursor.fetchall()]

        migrations_applied = []

        # Add activity_type if not exists
        if "activity_type" not in columns:
            print("Adding activity_type column...")
            cursor.execute("""
                ALTER TABLE plans
                ADD COLUMN activity_type VARCHAR(50) DEFAULT 'other'
            """)
            migrations_applied.append("activity_type")

        # Add completed_at if not exists
        if "completed_at" not in columns:
            print("Adding completed_at column...")
            cursor.execute("""
                ALTER TABLE plans
                ADD COLUMN completed_at DATETIME
            """)
            migrations_applied.append("completed_at")

        # Add extended_count if not exists
        if "extended_count" not in columns:
            print("Adding extended_count column...")
            cursor.execute("""
                ALTER TABLE plans
                ADD COLUMN extended_count INTEGER DEFAULT 0
            """)
            migrations_applied.append("extended_count")

        # Add last_checkin_at if not exists
        if "last_checkin_at" not in columns:
            print("Adding last_checkin_at column...")
            cursor.execute("""
                ALTER TABLE plans
                ADD COLUMN last_checkin_at DATETIME
            """)
            migrations_applied.append("last_checkin_at")

        # Check users table
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in cursor.fetchall()]

        # Add phone to users if not exists
        if "phone" not in user_columns:
            print("Adding phone column to users...")
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN phone VARCHAR(32)
            """)
            migrations_applied.append("users.phone")

        # Add last_login_at to users if not exists
        if "last_login_at" not in user_columns:
            print("Adding last_login_at column to users...")
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN last_login_at DATETIME
            """)
            migrations_applied.append("users.last_login_at")

        # Add is_active to users if not exists
        if "is_active" not in user_columns:
            print("Adding is_active column to users...")
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN is_active BOOLEAN DEFAULT 1
            """)
            migrations_applied.append("users.is_active")

        # Check devices table
        cursor.execute("PRAGMA table_info(devices)")
        device_columns = [col[1] for col in cursor.fetchall()]

        # Add env to devices if not exists
        if "env" not in device_columns:
            print("Adding env column to devices...")
            cursor.execute("""
                ALTER TABLE devices
                ADD COLUMN env VARCHAR(16) DEFAULT 'sandbox'
            """)
            migrations_applied.append("devices.env")

        # Add last_seen_at to devices if not exists
        if "last_seen_at" not in device_columns:
            print("Adding last_seen_at column to devices...")
            cursor.execute("""
                ALTER TABLE devices
                ADD COLUMN last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP
            """)
            migrations_applied.append("devices.last_seen_at")

        conn.commit()

        if migrations_applied:
            print(f"\n✅ Migration successful! Applied {len(migrations_applied)} changes:")
            for field in migrations_applied:
                print(f"   - {field}")
        else:
            print("✅ Database is already up to date")

        # Show current schema
        print("\n📊 Current database schema:")
        for table in ['users', 'plans', 'contacts', 'events', 'devices', 'login_tokens']:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = cursor.fetchall()
            if cols:
                print(f"\n{table}:")
                for col in cols:
                    print(f"  - {col[1]} ({col[2]})")

        return True

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)