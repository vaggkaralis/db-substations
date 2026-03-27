#!/usr/bin/env python3
import argparse
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from settings import DB_PATH


def _safe(value: str | None) -> str:
    return (value or "").replace("/", "-").replace("\\", "-").replace(":", "-")


def _win_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix _AUTO_SHORT report paths in DB")
    parser.add_argument(
        "--copy-missing-canonical",
        action="store_true",
        help="If canonical file is missing but _AUTO_SHORT file exists, copy to canonical and repoint DB",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT mrp.id, mrp.maintenance_id, mrp.element_id, mrp.report_path, e.name, s.name
        FROM maintenance_report_paths mrp
        JOIN elements e ON e.id = mrp.element_id
        JOIN substations s ON s.id = e.substation_id
        WHERE mrp.report_type = 'pdf' AND mrp.report_path LIKE '%\\_AUTO_SHORT\\%'
        """)
    rows = cur.fetchall() or []

    updated = 0
    copied = 0
    kept = 0
    missing = 0

    for (
        report_id,
        maintenance_id,
        _element_id,
        report_path,
        element_name,
        substation_name,
    ) in rows:
        safe_elem = _safe(element_name)
        safe_sub = _safe(substation_name)
        canonical_name = f"{safe_sub}_{safe_elem}_Maintenance_M{maintenance_id}.pdf"

        auto_short_dir = os.path.dirname(report_path)
        reports_subfolder = os.path.dirname(auto_short_dir)
        canonical_path = os.path.join(reports_subfolder, canonical_name)

        if os.path.isfile(canonical_path):
            cur.execute(
                "UPDATE maintenance_report_paths SET report_path=? WHERE id=?",
                (canonical_path, report_id),
            )
            updated += 1
        elif os.path.isfile(report_path):
            if args.copy_missing_canonical:
                os.makedirs(_win_path(os.path.dirname(canonical_path)), exist_ok=True)
                shutil.copy2(_win_path(report_path), _win_path(canonical_path))
                cur.execute(
                    "UPDATE maintenance_report_paths SET report_path=? WHERE id=?",
                    (canonical_path, report_id),
                )
                copied += 1
                updated += 1
            else:
                kept += 1
        else:
            missing += 1

    conn.commit()
    conn.close()

    print(
        f"checked={len(rows)} updated={updated} copied={copied} kept={kept} missing={missing}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
