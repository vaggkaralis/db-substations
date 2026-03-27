"""Deduplicate repeated crew members per maintenance by display name.

Keeps the first row and removes duplicate `maintenance_people` rows for role='crew'
when they map to the same normalized display name within the same maintenance.
By default runs in dry-run mode.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from settings import DB_PATH  # noqa: E402


def _find_duplicate_stats(
    conn: sqlite3.Connection, substation_id: int | None = None
) -> tuple[int, int]:
    cur = conn.cursor()
    sql = """
        WITH dup_groups AS (
          SELECT
            mp.maintenance_id,
            LOWER(TRIM(COALESCE(p.surname, p.name) || ' ' || COALESCE(p.given_name, ''))) AS display_name_key,
            COUNT(*) AS cnt
          FROM maintenance_people mp
          JOIN people p ON p.id = mp.person_id
          JOIN maintenance m ON m.id = mp.maintenance_id
          WHERE mp.role = 'crew'
    """
    params: list[object] = []
    if substation_id is not None:
        sql += " AND m.substation_id = ?"
        params.append(substation_id)
    sql += """
          GROUP BY mp.maintenance_id, display_name_key
          HAVING COUNT(*) > 1
        )
        SELECT COUNT(*), COALESCE(SUM(cnt - 1), 0)
        FROM dup_groups
    """
    cur.execute(sql, params)
    groups_count, extra_rows = cur.fetchone()
    return int(groups_count or 0), int(extra_rows or 0)


def dedupe_crew(
    db_path: str, substation_id: int | None = None, dry_run: bool = True
) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        groups_before, extras_before = _find_duplicate_stats(
            conn, substation_id=substation_id
        )

        result = {
            "duplicate_groups_before": groups_before,
            "extra_rows_before": extras_before,
            "deleted": 0,
            "duplicate_groups_after": groups_before,
            "extra_rows_after": extras_before,
        }

        if dry_run or extras_before == 0:
            return result

        cur = conn.cursor()
        sql = """
            WITH ranked AS (
              SELECT
                mp.id,
                ROW_NUMBER() OVER (
                  PARTITION BY
                    mp.maintenance_id,
                    mp.role,
                    LOWER(TRIM(COALESCE(p.surname, p.name) || ' ' || COALESCE(p.given_name, '')))
                  ORDER BY mp.id
                ) AS rn
              FROM maintenance_people mp
              JOIN people p ON p.id = mp.person_id
              JOIN maintenance m ON m.id = mp.maintenance_id
              WHERE mp.role = 'crew'
        """
        params: list[object] = []
        if substation_id is not None:
            sql += " AND m.substation_id = ?"
            params.append(substation_id)
        sql += """
            )
            DELETE FROM maintenance_people
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
        cur.execute(sql, params)

        conn.commit()

        groups_after, extras_after = _find_duplicate_stats(
            conn, substation_id=substation_id
        )
        result["deleted"] = max(0, extras_before - extras_after)
        result["duplicate_groups_after"] = groups_after
        result["extra_rows_after"] = extras_after
        return result
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deduplicate repeated crew names in maintenance_people."
    )
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database file")
    parser.add_argument(
        "--substation-id", type=int, default=None, help="Optional substation id filter"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply updates (default is dry-run)"
    )
    args = parser.parse_args()

    res = dedupe_crew(
        db_path=args.db, substation_id=args.substation_id, dry_run=not args.apply
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] duplicate_groups_before={res['duplicate_groups_before']}, "
        f"extra_rows_before={res['extra_rows_before']}, "
        f"deleted={res['deleted']}, "
        f"duplicate_groups_after={res['duplicate_groups_after']}, "
        f"extra_rows_after={res['extra_rows_after']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
