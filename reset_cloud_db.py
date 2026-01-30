"""
Script to reset the cloud database (database.db) with full schema.
Run this manually when needed to recreate the database structure.
"""

import sqlite3
import os

from database import init_db

# Delete old database
if os.path.exists('database.db'):
    os.remove('database.db')
    print("Deleted old database.db")

# Initialize new database with full schema
conn = init_db('database.db')
print("Initialized new database.db with full schema")

# Verify schema
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(elements)")
columns = [col[1] for col in cursor.fetchall()]
print(f"\nElements table has {len(columns)} columns:")
for col in columns:
    print(f"  - {col}")

conn.close()
print("\n✅ Database reset complete!")
