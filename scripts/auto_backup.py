#!/usr/bin/env python3
"""Create a tiered backup snapshot set for the configured DB.

Usage:
    python scripts/auto_backup.py
    python scripts/auto_backup.py --db path/to/substations.db --backup-root path/to/backups_auto --keep 3
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync_service import (
    maintain_backup_set,
    resolve_backup_root,
    resolve_db_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create tiered DB backup snapshots")
    parser.add_argument("--db", dest="db_path", default=None, help="Path to SQLite DB")
    parser.add_argument(
        "--backup-root", dest="backup_root", default=None, help="Backup root directory"
    )
    parser.add_argument(
        "--keep",
        dest="keep",
        type=int,
        default=3,
        help="How many hot snapshots to keep",
    )
    parser.add_argument(
        "--reason", dest="reason", default="scheduled", help="Backup reason label"
    )
    args = parser.parse_args()

    db_path = resolve_db_path(args.db_path)
    backup_root = args.backup_root or resolve_backup_root(db_path)

    summary = maintain_backup_set(
        db_path,
        backup_root,
        reason=args.reason,
        hot_keep=max(1, args.keep),
    )

    print("Backup completed")
    print(f"- DB: {db_path}")
    print(f"- Hot snapshot: {summary['created']['hot']}")
    print(f"- Backup root: {backup_root}")
    print(
        "- Tier snapshots: "
        f"daily={summary['created']['daily']} weekly={summary['created']['weekly']} monthly={summary['created']['monthly']}"
    )
    print(
        "- Removed old snapshots: "
        f"hot={len(summary['removed']['hot'])} daily={len(summary['removed']['daily'])} "
        f"weekly={len(summary['removed']['weekly'])} monthly={len(summary['removed']['monthly'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
