-- Fix NULL saved_contacts values in users table
-- This will set all NULL saved_contacts to an empty JSON object

UPDATE users
SET saved_contacts = '{}'::json
WHERE saved_contacts IS NULL;

-- Verify the fix
SELECT
    COUNT(*) as total_users,
    COUNT(saved_contacts) as users_with_contacts,
    COUNT(*) FILTER (WHERE saved_contacts IS NULL) as users_with_null
FROM users;