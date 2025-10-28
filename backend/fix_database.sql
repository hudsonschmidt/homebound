-- Quick fix for missing columns in production database
-- Run this in your database console (Render Shell, Supabase SQL Editor, etc.)

-- Add saved_contacts column to users table if it doesn't exist
ALTER TABLE users
ADD COLUMN IF NOT EXISTS saved_contacts JSON DEFAULT '{}';

-- Add location columns to plans table if they don't exist
ALTER TABLE plans
ADD COLUMN IF NOT EXISTS location_lat DOUBLE PRECISION;

ALTER TABLE plans
ADD COLUMN IF NOT EXISTS location_lng DOUBLE PRECISION;

-- Update alembic version to latest
INSERT INTO alembic_version (version_num)
VALUES ('ae8f29841bb8')
ON CONFLICT (version_num) DO NOTHING;

-- Verify the changes
SELECT
    'Users table - saved_contacts column added' as status,
    EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
        AND column_name = 'saved_contacts'
    ) as success

UNION ALL

SELECT
    'Plans table - location_lat column added' as status,
    EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'plans'
        AND column_name = 'location_lat'
    ) as success

UNION ALL

SELECT
    'Plans table - location_lng column added' as status,
    EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'plans'
        AND column_name = 'location_lng'
    ) as success;