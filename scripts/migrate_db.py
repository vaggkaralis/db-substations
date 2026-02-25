#!/usr/bin/env python3
"""Manage database schema migrations and version updates.

Usage:
    python migrate_db.py 2.0.0 "add_user_logs_table" 3.0.0
    python migrate_db.py --help

This script:
1. Updates db_metadata.json with new DB version
2. Creates a migration SQL file in migrations/ directory
3. Prints reminder to update DB_COMPATIBILITY in strings.py

The migration file can contain your SQL schema changes for documentation.
"""

import json
import os
import sys
from datetime import datetime

# Add parent directory to path to import strings module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def create_migration(version_new: str, migration_name: str, app_version: str) -> bool:
    """Create a database migration and update version metadata.
    
    Args:
        version_new: New database version (e.g., '2.0.0')
        migration_name: Descriptive name for the migration (e.g., 'add_user_logs_table')
        app_version: App version this migration targets (e.g., '3.0.0')
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate version format
        parts = version_new.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            print(f"✗ Invalid version format: {version_new}")
            print("  Use format: MAJOR.MINOR.PATCH (e.g., '2.0.0')")
            return False
        
        # Update db_metadata.json
        db_version_normalized = version_new.replace(".", "_")
        metadata = {
            "db_version": version_new,
            "last_migration": f"db_v{db_version_normalized}_{migration_name}",
            "created_at": datetime.now().isoformat(),
            "app_version_created": app_version
        }
        
        metadata_path = "db_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        print(f"✓ Updated {metadata_path} to version {version_new}")
        
        # Create migrations directory if it doesn't exist
        migrations_dir = "migrations"
        os.makedirs(migrations_dir, exist_ok=True)
        
        # Create migration file
        migration_filename = f"db_v{db_version_normalized}_{migration_name}.sql"
        migration_path = os.path.join(migrations_dir, migration_filename)
        
        migration_content = (
            f"-- Database Migration to Version {version_new}\n"
            f"-- Migration Name: {migration_name}\n"
            f"-- App Version: {app_version}\n"
            f"-- Created: {datetime.now().isoformat()}\n"
            f"--\n"
            f"-- TODO: Add your SQL schema changes below\n"
            f"--\n"
            f"-- Example:\n"
            f"-- ALTER TABLE maintenance ADD COLUMN created_by TEXT;\n"
            f"-- CREATE TABLE user_logs (id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, timestamp DATETIME);\n"
            f"\n"
        )
        
        with open(migration_path, "w", encoding="utf-8") as f:
            f.write(migration_content)
        
        print(f"✓ Created migration file: {migration_path}")
        
        # Print reminder about compatibility matrix
        print(f"\n{'='*70}")
        print(f"⚠️  IMPORTANT: Update DB_COMPATIBILITY in strings.py")
        print(f"{'='*70}")
        print(f"\nYou created DB version {version_new} for app {app_version}.")
        print(f"Update the compatibility matrix in strings.py:\n")
        print(f"    DB_COMPATIBILITY = {{")
        print(f"        \"2.0.0\": {{'min_db': \"1.0.0\", 'max_db': \"1.0.0'}},")
        print(f"        \"{app_version}\": {{'min_db': \"?.?.?\", 'max_db': \"{version_new}\"}},  # <- ADD THIS")
        print(f"    }}\n")
        print(f"Next steps:")
        print(f"1. Edit {migration_path} and add your SQL schema changes")
        print(f"2. Update DB_COMPATIBILITY in strings.py")
        print(f"3. Test the changes")
        print(f"4. Commit both files to git")
        
        return True
        
    except Exception as e:
        print(f"✗ Migration creation failed: {e}")
        return False


def print_help():
    """Print usage information."""
    print(__doc__)
    print("\nExamples:")
    print("  python scripts/migrate_db.py 2.0.0 add_user_logs_table 3.0.0")
    print("  python scripts/migrate_db.py 1.1.0 add_inspection_notes 2.1.0")


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] in ["--help", "-h", "help"]:
        print_help()
        sys.exit(0)
    
    if len(sys.argv) != 4:
        print("Error: Expected 3 arguments\n")
        print_help()
        sys.exit(1)
    
    version_new = sys.argv[1]
    migration_name = sys.argv[2]
    app_version = sys.argv[3]
    
    success = create_migration(version_new, migration_name, app_version)
    sys.exit(0 if success else 1)
