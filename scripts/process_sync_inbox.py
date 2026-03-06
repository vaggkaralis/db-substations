#!/usr/bin/env python3
"""Process OneDrive sync inbox and create rolling DB snapshots.

Usage:
    python scripts/process_sync_inbox.py
    python scripts/process_sync_inbox.py --db path/to/substations.db --sync-root path/to/sync_exchange
    python scripts/process_sync_inbox.py --hot-keep 3 --no-backup
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync_service import resolve_db_path, resolve_sync_root, resolve_backup_root, run_sync_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Process OneDrive inbox submissions")
    parser.add_argument("--db", dest="db_path", default=None, help="Path to authoritative SQLite DB")
    parser.add_argument("--sync-root", dest="sync_root", default=None, help="Path to sync_exchange root")
    parser.add_argument("--backup-root", dest="backup_root", default=None, help="Path to backup root")
    parser.add_argument("--actor", dest="actor", default="desktop", help="Actor label for audit events")
    parser.add_argument("--hot-keep", dest="hot_keep", type=int, default=3, help="How many hot snapshots to keep")
    parser.add_argument("--no-backup", dest="no_backup", action="store_true", help="Do not create snapshot on accepted changes")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db_path)
    sync_root = args.sync_root or resolve_sync_root(db_path)
    backup_root = args.backup_root or resolve_backup_root(db_path)

    conn = sqlite3.connect(db_path)
    try:
        summary = run_sync_cycle(
            conn,
            db_path=db_path,
            sync_root=sync_root,
            backup_root=backup_root,
            actor=args.actor,
            create_backup_on_change=not args.no_backup,
            hot_keep=args.hot_keep,
        )
        sync = summary["sync"]
        print("Sync cycle completed")
        print(f"- DB: {db_path}")
        print(f"- Sync root: {sync_root}")
        print(f"- Processed: {sync['processed']}")
        print(f"- Accepted: {sync['accepted']}")
        print(f"- Conflicts: {sync['conflicts']}")
        print(f"- Rejected: {sync['rejected']}")
        print(f"- Audit log: {sync['audit_log']}")
        if summary["snapshot"]:
            print(f"- Snapshot: {summary['snapshot']}")
        else:
            print("- Snapshot: (none)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
