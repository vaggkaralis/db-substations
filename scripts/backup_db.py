#!/usr/bin/env python3
"""Create versioned backups of the database and metadata.

Usage:
    python backup_db.py                          # Backup with auto-generated timestamp
    python backup_db.py "my_backup_description"  # Backup with custom description

This script:
1. Reads current DB version from db_metadata.json
2. Creates a backup directory: backups/{db_version}/
3. Copies database file (substations.db) to backup
4. Copies database metadata (db_metadata.json) to backup
5. Creates README.txt with backup info and optional description
"""

import shutil
import os
import sys
from datetime import datetime

# Add parent directory to path to import strings module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from settings import DB_PATH
    from strings import get_db_version_string
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this script from the project root directory.")
    sys.exit(1)


def backup_database(description: str = None) -> bool:
    """Create versioned backup of database + metadata.
    
    Args:
        description: Optional description text to include in README
    
    Returns:
        True if successful, False otherwise
    """
    try:
        db_version = get_db_version_string()
        backup_base_dir = "backups"
        backup_dir = os.path.join(backup_base_dir, db_version)
        
        # Create backup directory
        os.makedirs(backup_dir, exist_ok=True)
        
        # Backup the database file
        db_filename = os.path.basename(DB_PATH)
        backup_db_path = os.path.join(backup_dir, db_filename)
        shutil.copy(DB_PATH, backup_db_path)
        print(f"✓ Database backed up to: {backup_db_path}")
        
        # Backup metadata
        metadata_src = "db_metadata.json"
        metadata_dst = os.path.join(backup_dir, "db_metadata.json")
        shutil.copy(metadata_src, metadata_dst)
        print(f"✓ Metadata backed up to: {metadata_dst}")
        
        # Create README with backup info
        readme_path = os.path.join(backup_dir, "README.txt")
        timestamp = datetime.now().isoformat()
        
        readme_content = (
            f"Database Backup\n"
            f"{'='*60}\n"
            f"Version: {db_version}\n"
            f"Backed up: {timestamp}\n"
            f"Database file: {db_filename}\n\n"
        )
        
        if description:
            readme_content += f"Description:\n{description}\n\n"
        
        readme_content += (
            f"How to restore:\n"
            f"1. Copy {db_filename} from this directory to project root\n"
            f"2. Copy db_metadata.json from this directory to project root\n"
            f"3. Restart the application\n"
        )
        
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        
        print(f"✓ README created at: {readme_path}")
        print(f"\n✓ Complete backup created in: {backup_dir}")
        return True
        
    except Exception as e:
        print(f"✗ Backup failed: {e}")
        return False


if __name__ == "__main__":
    description = None
    if len(sys.argv) > 1:
        description = sys.argv[1]
    
    success = backup_database(description)
    sys.exit(0 if success else 1)
