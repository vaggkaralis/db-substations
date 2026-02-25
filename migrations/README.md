Database Migrations
==================

This directory contains SQL migration files for database schema changes.

Each migration file is named: `db_v{VERSION}_{NAME}.sql`

Example:
- `db_v1_0_0_initial_schema.sql` - Initial database schema
- `db_v2_0_0_add_user_logs_table.sql` - Add user activity logging
- `db_v2_1_0_add_inspection_notes.sql` - Add notes field to inspections

Usage
-----

Use the `scripts/migrate_db.py` script to create new migrations:

    python scripts/migrate_db.py 2.0.0 "add_user_logs_table" 3.0.0

This will:
1. Create a migration file: db_v2_0_0_add_user_logs_table.sql
2. Update db_metadata.json with version 2.0.0
3. Print a reminder to update DB_COMPATIBILITY in strings.py

Then:
1. Edit the migration file and add your SQL statements
2. Manually apply the SQL to the actual database
3. Test thoroughly
4. Update strings.py compatibility matrix
5. Commit to git

How Migrations Work
-------------------

Currently, migrations are:
- Created for documentation purposes
- Not automatically applied by the app

To apply a migration:
1. Open substations.db with a SQLite client
2. Copy the SQL from the migration file
3. Execute it in the database
4. Restart the app
5. Verify the changes work correctly

Future Enhancement
------------------

A migration runner could be added to automatically:
1. Detect unapplied migrations
2. Create a backup before applying
3. Execute migrations in order
4. Track applied migrations in a table
5. Show warnings if DB version != expected version
