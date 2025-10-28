# Database Migrations

This directory contains database migration scripts for the Homebound backend.

## Current Migrations

### 1. Add saved_contacts column to users table

This migration adds a JSON column to store saved emergency contacts for each user.

**Files:**
- `add_saved_contacts.sql` - Raw SQL migration
- `add_saved_contacts_production.py` - Python script for production migration

## Running Migrations

### Option 1: Using the Python Script (Recommended)

1. Set your database URL:
```bash
export DATABASE_URL="postgresql://username:password@host:port/database"
```

2. Run the migration:
```bash
cd backend/migrations
python add_saved_contacts_production.py
```

3. Follow the prompts and confirm when asked.

### Option 2: Using SQL directly

If you have direct database access (e.g., via psql, pgAdmin, or Supabase SQL editor):

1. Connect to your database
2. Run the SQL from `add_saved_contacts.sql`

For Supabase:
1. Go to the Supabase dashboard
2. Navigate to the SQL editor
3. Copy and paste the contents of `add_saved_contacts.sql`
4. Click "Run"

### Option 3: Using psql command line

```bash
psql $DATABASE_URL -f add_saved_contacts.sql
```

## Verification

After running the migration, verify it worked:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name = 'saved_contacts';
```

You should see:
```
column_name     | data_type
----------------+-----------
saved_contacts  | json
```

## Troubleshooting

If you get an error that the column already exists, that's fine - the migration has already been applied.

If you get permission errors, make sure your database user has ALTER TABLE privileges.

## Production Deployment

For production (Render.com):

1. SSH into your Render service or use the Shell tab in the Render dashboard
2. Set the DATABASE_URL if not already set
3. Run the Python migration script:
   ```bash
   cd backend/migrations
   python add_saved_contacts_production.py
   ```

Alternatively, you can run the SQL directly in your database management tool (pgAdmin, DBeaver, Supabase SQL Editor, etc.).