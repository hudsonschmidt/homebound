-- Migration: Add saved_contacts column to users table
-- This column stores saved emergency contacts for each user as JSON

-- Check if column exists and add it if it doesn't
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
        AND column_name = 'saved_contacts'
    ) THEN
        ALTER TABLE users
        ADD COLUMN saved_contacts JSON DEFAULT '{}'::json;

        RAISE NOTICE 'Column saved_contacts added successfully to users table';
    ELSE
        RAISE NOTICE 'Column saved_contacts already exists in users table';
    END IF;
END $$;

-- Verify the column was added
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name = 'saved_contacts';