#!/usr/bin/env python3
import sqlite3
import os
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from onedrive_hybrid_storage import (
        resolve_shared_root,
        retrofit_shared_root_paths,
    )
    from settings import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    try:
        stats = retrofit_shared_root_paths(conn, db_path=DB_PATH)
        shared_root = resolve_shared_root(DB_PATH)
    finally:
        conn.close()

    print(f"Shared root: {shared_root}")
    print(f"maintenance_storage_paths updated: {stats['storage_rows_updated']}")
    print(f"maintenance media links updated: {stats['maintenance_links_updated']}")
    print(f"maintenance_report_paths updated: {stats['report_paths_updated']}")
    print(
        "maintenance_overview_report_paths updated: "
        f"{stats['overview_report_paths_updated']}"
    )
    print(f"dga_measurements report_path updated: {stats['dga_report_paths_updated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
