"""Sanitize imported email maintenance comments in the database.

Removes forwarded/replied history and mail header/recipient blocks from
existing maintenance.overall_comments using the same logic as current imports.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_eml_parser import sanitize_email_body_for_import
from settings import DB_PATH


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def sanitize_existing_comments(
    db_path: str,
    substation_name: str | None = None,
    substation_id: int | None = None,
    dry_run: bool = True,
) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        columns = _table_columns(conn, "maintenance")
        has_type = "maintenance_type" in columns

        query = (
            "SELECT m.id, m.overall_comments "
            "FROM maintenance m "
            "JOIN substations s ON s.id = m.substation_id "
            "WHERE COALESCE(m.overall_comments, '') <> ''"
        )
        params: list[str] = []

        if has_type:
            query += " AND COALESCE(m.maintenance_type, '') = 'Email'"

        if substation_id is not None:
            query += " AND s.id = ?"
            params.append(str(substation_id))
        elif substation_name:
            query += " AND s.name = ?"
            params.append(substation_name)

        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()

        scanned = len(rows)
        updated = 0

        for maintenance_id, comments in rows:
            cleaned = sanitize_email_body_for_import(comments or "")
            if cleaned == (comments or ""):
                continue
            updated += 1
            if not dry_run:
                cur.execute(
                    "UPDATE maintenance SET overall_comments=? WHERE id=?",
                    (cleaned, maintenance_id),
                )

        if not dry_run:
            conn.commit()

        return scanned, updated
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize existing imported email maintenance comments."
    )
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database file")
    parser.add_argument(
        "--substation", default=None, help="Optional exact substation name filter"
    )
    parser.add_argument(
        "--substation-id", type=int, default=None, help="Optional substation id filter"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. By default, runs in dry-run mode.",
    )
    args = parser.parse_args()

    scanned, updated = sanitize_existing_comments(
        db_path=args.db,
        substation_name=args.substation,
        substation_id=args.substation_id,
        dry_run=not args.apply,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] scanned={scanned}, would_update={updated}"
        if not args.apply
        else f"[{mode}] scanned={scanned}, updated={updated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
