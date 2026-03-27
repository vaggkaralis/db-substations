"""
Clear all maintenance history from the database.

This script will:
1. Delete all records from the maintenance table (which cascades to maintenance_elements and maintenance_people)
2. Reset the maintenance_date field in the elements table to NULL
3. Reset the last_maintenance_date field in the substations table to NULL

WARNING: This operation cannot be undone!
"""

import sqlite3
import sys
from pathlib import Path

from settings import DB_PATH


def clear_maintenance_history(db_path=None):
    """Clear all maintenance history from the database."""
    if db_path is None:
        db_path = DB_PATH

    # Confirm action
    print(f"Database: {db_path}")
    print("\n⚠️  WARNING: This will permanently delete ALL maintenance history!")
    print("This includes:")
    print("  - All maintenance records")
    print("  - All maintenance-element associations")
    print("  - All maintenance-people associations")
    print("  - Will reset last maintenance dates on all elements")
    print("  - Will reset last maintenance dates on all substations")

    response = input("\nAre you sure you want to continue? Type 'YES' to confirm: ")

    if response != "YES":
        print("Operation cancelled.")
        return False

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    try:
        # Count records before deletion
        c.execute("SELECT COUNT(*) FROM maintenance")
        maintenance_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM maintenance_elements")
        elements_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM maintenance_people")
        people_count = c.fetchone()[0]

        print(f"\nFound:")
        print(f"  - {maintenance_count} maintenance records")
        print(f"  - {elements_count} maintenance-element associations")
        print(f"  - {people_count} maintenance-people associations")

        if maintenance_count == 0:
            print("\nNo maintenance records to delete.")
            conn.close()
            return True

        print("\nDeleting maintenance history...")

        # Delete all maintenance records (cascades to maintenance_elements and maintenance_people)
        c.execute("DELETE FROM maintenance")

        # Reset maintenance_date in elements table
        c.execute("UPDATE elements SET maintenance_date = NULL")
        updated_elements = c.rowcount

        # Reset last_maintenance_date in substations table (if column exists)
        try:
            c.execute("UPDATE substations SET last_maintenance_date = NULL")
            updated_substations = c.rowcount
        except sqlite3.OperationalError:
            # Column might not exist in older schemas
            updated_substations = 0

        conn.commit()

        print(f"\n✅ Successfully cleared maintenance history:")
        print(f"  - Deleted {maintenance_count} maintenance records")
        print(
            f"  - Deleted {elements_count} maintenance-element associations (cascaded)"
        )
        print(f"  - Deleted {people_count} maintenance-people associations (cascaded)")
        print(f"  - Reset maintenance dates on {updated_elements} elements")
        if updated_substations > 0:
            print(f"  - Reset maintenance dates on {updated_substations} substations")

        return True

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        db_path = None

    success = clear_maintenance_history(db_path)
    sys.exit(0 if success else 1)
