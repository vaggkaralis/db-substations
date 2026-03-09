"""Recompute maintenance_elements for imported email maintenances.

Uses current maintenance.overall_comments and the shared element extraction logic.
By default runs in dry-run mode.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_email_importer import _find_elements_in_body
from settings import DB_PATH


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def recompute_elements(
    db_path: str,
    substation_id: int | None = None,
    dry_run: bool = True,
    force: bool = False,
) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        cols = _table_columns(conn, "maintenance")
        has_type = "maintenance_type" in cols

        query = (
            "SELECT id, substation_id, COALESCE(overall_comments, '') "
            "FROM maintenance "
            "WHERE COALESCE(overall_comments, '') <> ''"
        )
        params: list[object] = []

        if has_type:
            query += " AND COALESCE(maintenance_type, '') = 'Email'"
        if substation_id is not None:
            query += " AND substation_id = ?"
            params.append(substation_id)

        query += " ORDER BY id"

        cur = conn.cursor()
        cur.execute(query, params)
        maint_rows = cur.fetchall()

        summary = {
            "scanned": len(maint_rows),
            "would_change": 0,
            "updated": 0,
            "protected_skips": 0,
            "unchanged": 0,
            "errors": 0,
        }

        for maintenance_id, sid, comments in maint_rows:
            try:
                inferred_ids = _find_elements_in_body(conn, comments or "", sid)

                cur.execute(
                    "SELECT id, element_id, COALESCE(element_comments, '') FROM maintenance_elements WHERE maintenance_id=?",
                    (maintenance_id,),
                )
                existing_rows = cur.fetchall()
                existing_ids = {row[1] for row in existing_rows}
                has_non_empty_comments = any((row[2] or "").strip() for row in existing_rows)

                if inferred_ids == existing_ids:
                    summary["unchanged"] += 1
                    continue

                if has_non_empty_comments and not force:
                    summary["protected_skips"] += 1
                    continue

                summary["would_change"] += 1
                if not dry_run:
                    cur.execute("DELETE FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,))
                    for elem_id in sorted(inferred_ids):
                        cur.execute(
                            "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, '')",
                            (maintenance_id, elem_id),
                        )
                    summary["updated"] += 1
            except Exception:
                summary["errors"] += 1

        if not dry_run:
            conn.commit()

        return summary
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute maintenance elements from email comments.")
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database file")
    parser.add_argument("--substation-id", type=int, default=None, help="Optional substation id filter")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default is dry-run)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Also update maintenances that have non-empty element comments",
    )
    args = parser.parse_args()

    result = recompute_elements(
        db_path=args.db,
        substation_id=args.substation_id,
        dry_run=not args.apply,
        force=args.force,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] scanned={result['scanned']}, "
        f"would_change={result['would_change']}, "
        f"updated={result['updated']}, "
        f"protected_skips={result['protected_skips']}, "
        f"unchanged={result['unchanged']}, "
        f"errors={result['errors']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
