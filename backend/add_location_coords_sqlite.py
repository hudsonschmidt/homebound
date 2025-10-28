#!/usr/bin/env python3
"""
Migration script to add location coordinate columns to the SQLite plans table.
This adds location_lat and location_lng columns to store geographic coordinates
for trip locations, enabling future location-based features and statistics.
"""

import sqlite3
from pathlib import Path


def add_location_columns():
    """Add location_lat and location_lng columns to plans table in SQLite."""

    # Path to the SQLite database
    db_path = Path("homebound.db")

    if not db_path.exists():
        print(f"Database file {db_path} not found")
        return

    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("Checking existing columns in plans table...")

        # Get current table info
        cursor.execute("PRAGMA table_info(plans)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        # Check if columns already exist
        has_lat = 'location_lat' in column_names
        has_lng = 'location_lng' in column_names

        if has_lat and has_lng:
            print("Location columns already exist in plans table")
            return

        # Add location_lat column if it doesn't exist
        if not has_lat:
            cursor.execute("""
                ALTER TABLE plans
                ADD COLUMN location_lat REAL DEFAULT NULL
            """)
            print("Added location_lat column to plans table")

        # Add location_lng column if it doesn't exist
        if not has_lng:
            cursor.execute("""
                ALTER TABLE plans
                ADD COLUMN location_lng REAL DEFAULT NULL
            """)
            print("Added location_lng column to plans table")

        # Commit the changes
        conn.commit()

        # Verify columns were added
        cursor.execute("PRAGMA table_info(plans)")
        columns = cursor.fetchall()

        print("\nVerification - All columns in plans table:")
        for col_info in columns:
            col_id, name, dtype, notnull, default, pk = col_info
            if name in ['location_lat', 'location_lng']:
                print(f"  ✓ {name}: {dtype} (nullable: {'No' if notnull else 'Yes'})")

        print("\nMigration completed successfully!")
        print("Plans can now store location coordinates for future location-based features.")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    add_location_columns()