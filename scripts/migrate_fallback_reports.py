#!/usr/bin/env python3
"""
Migrate reports from _AUTO_SHORT_REPORTS fallback location to proper storage paths.

This script:
1. Scans _AUTO_SHORT_REPORTS for maintenance reports
2. Determines proper storage location for each
3. Creates missing storage_paths if needed
4. Moves reports to proper locations
5. Updates database
6. Cleans up empty directories
"""

import os
import sys
import shutil
import sqlite3
import re
import filecmp
import argparse

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def win_path(path):
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def get_shared_root():
    """Get the shared reports root path."""
    from onedrive_hybrid_storage import resolve_shared_root
    from settings import DB_PATH

    return resolve_shared_root(DB_PATH)


def parse_report_filename(filename):
    """Extract maintenance_id and element_id from report filename.

    Filenames are like:
    - Old format 1: Maintenance_M2_E1201_ΜΣ2.pdf
    - Old format 2: M2_E1201.pdf
    - New format: ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ_Ρ-15_Maintenance_M190.pdf (no element_id in name)
      For new format, we extract from database instead
    """
    # Try format: Maintenance_M{mid}_E{eid}_*.pdf
    match = re.match(r"Maintenance_M(\d+)_E(\d+)_.*\.pdf", filename)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Try format: M{mid}_E{eid}.pdf
    match = re.match(r"M(\d+)_E(\d+)\.pdf", filename)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Try new format: {substation}_{element}_Maintenance_M{mid}.pdf
    match = re.match(r".*_Maintenance_M(\d+)\.pdf", filename)
    if match:
        # For new format, we can only extract maintenance_id
        # Element ID needs to be looked up from database
        return int(match.group(1)), None

    return None, None


def safe_name(value):
    return (value or "").replace("/", "-").replace("\\", "-").replace(":", "-")


def canonical_report_name(substation_name, element_name, maintenance_id):
    return (
        f"{safe_name(substation_name)}_{safe_name(element_name)}"
        f"_Maintenance_M{maintenance_id}.pdf"
    )


def build_target_path(conn, db_path, maintenance_id, element_row):
    from onedrive_hybrid_storage import (
        _report_subfolder_name_for_element,
        get_transformer_report_targets,
    )

    element_id = element_row["element_id"]
    gate_value = element_row["gate"]
    targets = get_transformer_report_targets(
        conn,
        maintenance_id=maintenance_id,
        gate_value=gate_value,
        db_path=db_path,
    )
    if not targets:
        raise RuntimeError(
            f"No report targets found for M{maintenance_id}_E{element_id}"
        )

    reports_root = targets[0]
    subfolder = os.path.join(
        reports_root,
        _report_subfolder_name_for_element(element_row["element_type"]),
    )
    os.makedirs(win_path(subfolder), exist_ok=True)
    return os.path.join(
        subfolder,
        canonical_report_name(
            element_row["substation_name"],
            element_row["element_name"],
            maintenance_id,
        ),
    )


def prune_empty_dirs(root_path):
    if not os.path.isdir(root_path):
        return
    for dirpath, _dirnames, _filenames in os.walk(root_path, topdown=False):
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError:
            pass


def fetch_maintenance_rows(cursor, maintenance_id):
    cursor.execute(
        """
        SELECT m.substation_id,
               m.name AS maintenance_name,
               m.maintenance_type,
               m.date_time,
               s.name AS substation_name,
               e.id AS element_id,
               e.name AS element_name,
               e.element_type,
               e.gate
        FROM maintenance m
        JOIN substations s ON s.id = m.substation_id
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        JOIN elements e ON e.id = me.element_id
        WHERE m.id = ?
        ORDER BY e.id
        """,
        (maintenance_id,),
    )
    return cursor.fetchall() or []


def match_files_to_elements(maintenance_id, source_files, element_rows):
    assignments = {}
    unmatched_files = []
    unmatched_elements = {row["element_id"]: row for row in element_rows}

    exact_name_map = {
        canonical_report_name(
            row["substation_name"], row["element_name"], maintenance_id
        ).lower(): row["element_id"]
        for row in element_rows
    }
    element_token_map = {
        row["element_id"]: safe_name(row["element_name"]).lower()
        for row in element_rows
    }

    for source_file in source_files:
        filename = os.path.basename(source_file)
        lower_name = filename.lower()
        _mid, explicit_eid = parse_report_filename(filename)
        target_eid = None

        if explicit_eid in unmatched_elements:
            target_eid = explicit_eid
        elif (
            lower_name in exact_name_map
            and exact_name_map[lower_name] in unmatched_elements
        ):
            target_eid = exact_name_map[lower_name]
        else:
            candidate_ids = []
            for element_id, token in element_token_map.items():
                if element_id not in unmatched_elements:
                    continue
                if token and token in lower_name:
                    candidate_ids.append(element_id)
            if len(candidate_ids) == 1:
                target_eid = candidate_ids[0]

        if target_eid is None:
            unmatched_files.append(source_file)
            continue

        assignments[target_eid] = source_file
        unmatched_elements.pop(target_eid, None)

    if len(unmatched_files) == 1 and len(unmatched_elements) == 1:
        only_eid = next(iter(unmatched_elements))
        assignments[only_eid] = unmatched_files.pop()
        unmatched_elements.pop(only_eid, None)

    return assignments, unmatched_files, list(unmatched_elements.values())


def migrate_fallback_reports(*, conflict_policy: str = "skip"):
    """Main migration logic."""
    from onedrive_hybrid_storage import (
        ensure_maintenance_folders,
        upsert_maintenance_report_path,
    )
    from settings import DB_PATH

    db_path = DB_PATH
    shared_root = get_shared_root()

    if not shared_root:
        print("ERROR: Could not determine shared_root path")
        return 1

    fallback_root = os.path.join(shared_root, "_AUTO_SHORT_REPORTS")
    if not os.path.exists(fallback_root):
        print(f"No fallback directory found at {fallback_root}")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    stats = {
        "scanned": 0,
        "moved": 0,
        "removed_duplicates": 0,
        "db_pointed_to_canonical_on_conflict": 0,
        "unmatched_files": 0,
        "conflicts": 0,
        "errors": 0,
        "storage_paths_created": 0,
        "db_updated": 0,
    }
    maintenance_dirs = []

    for maint_dir in os.listdir(fallback_root):
        maint_path = os.path.join(fallback_root, maint_dir)
        if not os.path.isdir(maint_path):
            continue

        # Extract maintenance ID from folder name (e.g., "M2" -> 2)
        match = re.match(r"M(\d+)$", maint_dir)
        if not match:
            continue
        maintenance_dirs.append((int(match.group(1)), maint_path))

    print(f"Found {len(maintenance_dirs)} maintenance fallback folders\n")

    # Now process each maintenance
    cursor = conn.cursor()
    for maintenance_id, maint_path in sorted(maintenance_dirs):
        try:
            source_files = []
            for root, _dirs, files in os.walk(maint_path):
                for filename in files:
                    if filename.lower().endswith(".pdf"):
                        source_files.append(os.path.join(root, filename))

            if not source_files:
                continue

            source_files.sort()
            stats["scanned"] += len(source_files)

            element_rows = fetch_maintenance_rows(cursor, maintenance_id)
            if not element_rows:
                print(f"M{maintenance_id}: No maintenance/element rows found")
                stats["errors"] += len(source_files)
                continue

            maintenance_row = element_rows[0]

            # Check if maintenance has storage paths
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM maintenance_storage_paths "
                "WHERE maintenance_id = ?",
                (maintenance_id,),
            )
            has_paths = cursor.fetchone()["cnt"] > 0

            if not has_paths:
                # Create storage paths by calling ensure_maintenance_folders
                print(f"M{maintenance_id}: Creating storage paths...")
                try:
                    ensure_maintenance_folders(
                        conn,
                        maintenance_id=maintenance_id,
                        substation_id=maintenance_row["substation_id"],
                        maintenance_name=maintenance_row["maintenance_name"],
                        maintenance_type=maintenance_row["maintenance_type"],
                        date_time=maintenance_row["date_time"],
                        element_ids=[row["element_id"] for row in element_rows],
                        attachment_paths=[],
                        db_path=db_path,
                    )
                    stats["storage_paths_created"] += 1
                    has_paths = True
                except Exception as e:
                    print(f"  ERROR creating paths: {e}")
                    stats["errors"] += 1
                    has_paths = False

            if not has_paths:
                print(f"M{maintenance_id}: Could not create storage paths, skipping")
                continue

            assignments, unmatched_files, unmatched_elements = match_files_to_elements(
                maintenance_id,
                source_files,
                element_rows,
            )

            if unmatched_files:
                stats["unmatched_files"] += len(unmatched_files)
                print(f"M{maintenance_id}: {len(unmatched_files)} unmatched file(s)")
                for source_file in unmatched_files[:5]:
                    print(f"  UNMATCHED FILE: {os.path.basename(source_file)}")

            if unmatched_elements:
                print(
                    f"M{maintenance_id}: {len(unmatched_elements)} unmatched element(s)"
                )
                for row in unmatched_elements[:5]:
                    print(
                        f"  UNMATCHED ELEMENT: E{row['element_id']} "
                        f"{row['element_name']}"
                    )

            element_by_id = {row["element_id"]: row for row in element_rows}
            for element_id, source_file in sorted(assignments.items()):
                try:
                    target_file = build_target_path(
                        conn, db_path, maintenance_id, element_by_id[element_id]
                    )
                    source_abs = os.path.abspath(source_file)
                    target_abs = os.path.abspath(target_file)
                    source_fs = win_path(source_abs)
                    target_fs = win_path(target_abs)
                    final_db_path = target_abs

                    if os.path.normcase(source_abs) == os.path.normcase(target_abs):
                        pass
                    elif os.path.exists(target_fs):
                        if filecmp.cmp(source_fs, target_fs, shallow=False):
                            os.remove(source_fs)
                            stats["removed_duplicates"] += 1
                            print(
                                f"  M{maintenance_id}_E{element_id}: "
                                "Removed duplicate fallback copy"
                            )
                        else:
                            if conflict_policy == "prefer-canonical":
                                stats["db_pointed_to_canonical_on_conflict"] += 1
                                print(
                                    f"  M{maintenance_id}_E{element_id}: "
                                    "Conflict at target, DB pointed to canonical"
                                )
                            else:
                                final_db_path = source_abs
                                print(
                                    f"  M{maintenance_id}_E{element_id}: "
                                    "Conflict at target, keeping fallback file"
                                )
                            stats["conflicts"] += 1
                    else:
                        os.makedirs(
                            win_path(os.path.dirname(target_abs)), exist_ok=True
                        )
                        shutil.move(source_fs, target_fs)
                        stats["moved"] += 1
                        print(
                            f"  M{maintenance_id}_E{element_id}: "
                            f"Moved -> {os.path.relpath(target_abs, shared_root)}"
                        )
                        final_db_path = target_abs

                    # Update database
                    upsert_maintenance_report_path(
                        conn,
                        maintenance_id=maintenance_id,
                        element_id=element_id,
                        report_type="pdf",
                        report_path=final_db_path,
                    )
                    stats["db_updated"] += 1

                except Exception as e:
                    print(
                        f"  M{maintenance_id}_E{element_id}: Error moving report: {e}"
                    )
                    stats["errors"] += 1

            prune_empty_dirs(maint_path)

        except Exception as e:
            print(f"M{maintenance_id}: Error processing: {e}")
            stats["errors"] += 1

    # Cleanup: Remove empty directories
    print("\nCleaning up empty directories...")
    prune_empty_dirs(fallback_root)

    # Try to remove fallback_root if empty
    try:
        if not any(os.scandir(fallback_root)):
            os.rmdir(fallback_root)
            print("  Removed: _AUTO_SHORT_REPORTS (empty)")
    except Exception:
        print("  _AUTO_SHORT_REPORTS still has content")

    conn.commit()
    conn.close()

    # Print summary
    print("\n=== MIGRATION SUMMARY ===")
    print(f"Reports scanned: {stats['scanned']}")
    print(f"Reports moved: {stats['moved']}")
    print(f"Duplicate fallback copies removed: {stats['removed_duplicates']}")
    print(
        "Conflicts pointed to canonical in DB: "
        f"{stats['db_pointed_to_canonical_on_conflict']}"
    )
    print(f"Storage paths created: {stats['storage_paths_created']}")
    print(f"DB updates: {stats['db_updated']}")
    print(f"Unmatched files: {stats['unmatched_files']}")
    print(f"Conflicts: {stats['conflicts']}")
    print(f"Errors: {stats['errors']}")

    return 0 if stats["errors"] == 0 and stats["unmatched_files"] == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate fallback reports into canonical paths"
    )
    parser.add_argument(
        "--conflict-policy",
        choices=["skip", "prefer-canonical"],
        default="skip",
        help="Policy on file conflicts: 'skip' or 'prefer-canonical'.",
    )
    args = parser.parse_args()
    sys.exit(migrate_fallback_reports(conflict_policy=args.conflict_policy))
