import json
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from config_manager import get_app_setting
from settings import DB_PATH


BACKUP_TIER_ORDER = ("hot", "daily", "weekly", "monthly")
BACKUP_TIER_KEEP_DEFAULTS = {
    "hot": 3,
    "daily": 2,
    "weekly": 2,
    "monthly": 2,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _safe_move(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)


def _load_processed_tracker(tracker_path: str) -> dict:
    """Load the processed files tracker."""
    if os.path.exists(tracker_path):
        try:
            with open(tracker_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


def _save_processed_tracker(tracker_path: str, tracker: dict) -> None:
    """Save the processed files tracker."""
    os.makedirs(os.path.dirname(tracker_path), exist_ok=True)
    with open(tracker_path, "w", encoding="utf-8") as fh:
        json.dump(tracker, fh, ensure_ascii=False, indent=2)


_IDEMPOTENT_COMPARISON_IGNORED_FIELDS = {
    "elements": {"maintenance_date"},
}


def _record_exists_with_data(cur, table: str, record_id, expected_data: dict) -> str:
    """Check if record exists. Returns: 'none', 'identical', or 'different'."""
    if not record_id:
        return "none"

    try:
        cur.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,))
        row = cur.fetchone()
        if not row:
            return "none"

        # Get column names
        cols = [col[0] for col in cur.description]
        existing_data = dict(zip(cols, row))
        ignored_fields = _IDEMPOTENT_COMPARISON_IGNORED_FIELDS.get(table, set())

        # Compare only the keys present in expected_data
        for key in expected_data:
            if key in ignored_fields:
                continue
            if key in existing_data:
                existing_value = (
                    "" if existing_data[key] is None else existing_data[key]
                )
                expected_value = (
                    "" if expected_data[key] is None else expected_data[key]
                )
                if str(existing_value) != str(expected_value):
                    return "different"

        return "identical"
    except Exception:
        return "none"


def _apply_generic_table_change(
    cur,
    conn: sqlite3.Connection,
    table: str,
    op: str,
    data: dict,
) -> str:
    """Apply a simple id-based insert/update/delete change.

    Returns one of: accepted, already_applied, conflict, ignored.
    """
    record_id = data.get("id")

    if op == "delete":
        if not record_id:
            return "conflict"
        cur.execute(f"SELECT 1 FROM {table} WHERE id=?", (record_id,))
        if not cur.fetchone():
            return "already_applied"
        cur.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
        conn.commit()
        return "accepted"

    cols_info = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]

    if op == "update":
        if not record_id:
            return "conflict"
        cur.execute(f"SELECT 1 FROM {table} WHERE id=?", (record_id,))
        if not cur.fetchone():
            return "conflict"

        update_keys = [k for k in data.keys() if k in cols_info and k != "id"]
        if not update_keys:
            return "ignored"

        assignments = ",".join([f"{key}=?" for key in update_keys])
        cur.execute(
            f"UPDATE {table} SET {assignments} WHERE id=?",
            [data[key] for key in update_keys] + [record_id],
        )
        conn.commit()
        return "accepted"

    if op != "insert":
        return "ignored"

    if record_id:
        existence = _record_exists_with_data(cur, table, record_id, data)
        if existence == "identical":
            return "already_applied"
        if existence == "different":
            return "conflict"

    insert_keys = [k for k in data.keys() if k in cols_info]
    if not insert_keys:
        return "ignored"

    placeholders = ",".join(["?"] * len(insert_keys))
    columns = ",".join(insert_keys)
    try:
        cur.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            [data[k] for k in insert_keys],
        )
        conn.commit()
        return "accepted"
    except sqlite3.IntegrityError:
        conn.rollback()
        return "conflict"


def _apply_isolation_request_change(
    cur,
    conn: sqlite3.Connection,
    op: str,
    data: dict,
) -> str:
    request_id = data.get("id")
    request_cols = [r[1] for r in cur.execute("PRAGMA table_info(isolation_requests)")]

    if op == "delete":
        if not request_id:
            return "conflict"
        cur.execute("SELECT 1 FROM isolation_requests WHERE id=?", (request_id,))
        if not cur.fetchone():
            return "already_applied"
        cur.execute(
            "UPDATE maintenance SET isolation_request_id=NULL WHERE isolation_request_id=?",
            (request_id,),
        )
        cur.execute(
            "DELETE FROM isolation_request_elements WHERE request_id=?", (request_id,)
        )
        cur.execute("DELETE FROM isolation_requests WHERE id=?", (request_id,))
        conn.commit()
        return "accepted"

    element_ids = []
    for elem in data.get("elements") or []:
        elem_id = elem.get("element_id") or elem.get("id")
        if elem_id:
            element_ids.append(elem_id)

    if op == "update":
        if not request_id:
            return "conflict"
        cur.execute("SELECT 1 FROM isolation_requests WHERE id=?", (request_id,))
        if not cur.fetchone():
            return "conflict"

        update_keys = [k for k in data.keys() if k in request_cols and k != "id"]
        if update_keys:
            assignments = ",".join([f"{key}=?" for key in update_keys])
            cur.execute(
                f"UPDATE isolation_requests SET {assignments} WHERE id=?",
                [data[key] for key in update_keys] + [request_id],
            )
        if "elements" in data:
            cur.execute(
                "DELETE FROM isolation_request_elements WHERE request_id=?",
                (request_id,),
            )
            for elem_id in sorted(set(element_ids)):
                cur.execute(
                    "INSERT OR IGNORE INTO isolation_request_elements (request_id, element_id) VALUES (?, ?)",
                    (request_id, elem_id),
                )
        conn.commit()
        return "accepted"

    if op != "insert":
        return "ignored"

    if request_id:
        existence = _record_exists_with_data(
            cur, "isolation_requests", request_id, data
        )
        if existence == "identical":
            return "already_applied"
        if existence == "different":
            return "conflict"

    insert_keys = [k for k in data.keys() if k in request_cols]
    if not insert_keys:
        return "ignored"

    placeholders = ",".join(["?"] * len(insert_keys))
    columns = ",".join(insert_keys)
    try:
        cur.execute(
            f"INSERT INTO isolation_requests ({columns}) VALUES ({placeholders})",
            [data[k] for k in insert_keys],
        )
        request_id = request_id or cur.lastrowid
        for elem_id in sorted(set(element_ids)):
            cur.execute(
                "INSERT OR IGNORE INTO isolation_request_elements (request_id, element_id) VALUES (?, ?)",
                (request_id, elem_id),
            )
        conn.commit()
        return "accepted"
    except sqlite3.IntegrityError:
        conn.rollback()
        return "conflict"


def resolve_db_path(explicit_db_path: str | None = None) -> str:
    if explicit_db_path:
        return os.path.abspath(explicit_db_path)
    configured = get_app_setting("db_path", None)
    return os.path.abspath(configured or DB_PATH)


def resolve_sync_root(db_path: str | None = None) -> str:
    configured = get_app_setting("sync_root_path", None)
    if configured:
        return os.path.abspath(configured)
    effective_db = resolve_db_path(db_path)
    return os.path.join(os.path.dirname(effective_db), "sync_exchange")


def resolve_backup_root(db_path: str | None = None) -> str:
    configured = str(get_app_setting("backup_root_path", "") or "").strip()
    effective_db = resolve_db_path(db_path)
    base_dir = os.path.dirname(effective_db) if effective_db else os.getcwd()

    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        if os.path.isabs(expanded):
            return os.path.abspath(expanded)
        return os.path.abspath(os.path.join(base_dir, expanded))

    return os.path.join(os.path.abspath(base_dir), "backups_auto")


def ensure_sync_tree(sync_root: str) -> dict[str, str]:
    paths = {
        "inbox_pending": os.path.join(sync_root, "inbox", "pending"),
        "accepted": os.path.join(sync_root, "inbox", "processed", "accepted"),
        "rejected": os.path.join(sync_root, "inbox", "processed", "rejected"),
        "conflicts": os.path.join(sync_root, "inbox", "processed", "conflicts"),
        "logs": os.path.join(sync_root, "logs"),
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths


def _append_jsonl(path: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _summarize_change_file(file_path: str) -> dict:
    """Return lightweight summary metadata for one JSON/JSONL change file."""
    entries = 0
    insert_entries = 0
    table_counts: dict[str, int] = {}

    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = (raw_line or "").strip()
                if not line:
                    continue
                entries += 1
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("operation") != "insert":
                    continue
                insert_entries += 1
                table = str(obj.get("table") or "unknown")
                table_counts[table] = int(table_counts.get(table, 0) or 0) + 1
    except Exception:
        pass

    return {
        "entries": int(entries),
        "insert_entries": int(insert_entries),
        "table_counts": table_counts,
    }


def _refresh_maintenance_dates(cur, substation_id, element_ids) -> None:
    unique_ids = sorted({int(x) for x in (element_ids or []) if x is not None})
    for element_id in unique_ids:
        cur.execute(
            """
            SELECT m.date_time
            FROM maintenance m
            JOIN maintenance_elements me ON me.maintenance_id = m.id
            WHERE me.element_id = ?
            ORDER BY m.date_time DESC
            LIMIT 1
            """,
            (element_id,),
        )
        row = cur.fetchone()
        new_date = row[0] if row else None
        cur.execute(
            "UPDATE elements SET maintenance_date=? WHERE id=?",
            (new_date, element_id),
        )

    if substation_id is not None:
        cur.execute(
            "SELECT MAX(date_time) FROM maintenance WHERE substation_id=?",
            (substation_id,),
        )
        row = cur.fetchone()
        new_sub_date = row[0] if row and row[0] else None
        cur.execute(
            "UPDATE substations SET last_maintenance=? WHERE id=?",
            (new_sub_date, substation_id),
        )


def _apply_change_log_to_db(
    conn: sqlite3.Connection,
    file_path: str,
    tracker: dict | None = None,
    filename: str | None = None,
) -> tuple[int, int, int]:
    """
    Apply changes from a JSONL file to the database (idempotent).

    Args:
        conn: Database connection
        file_path: Path to the JSONL change file
        tracker: Optional processed files tracker dict
        filename: Filename for tracking (defaults to basename of file_path)

    Returns:
        Tuple of (accepted, already_applied, conflicts)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    if filename is None:
        filename = os.path.basename(file_path)

    if tracker is None:
        tracker = {}

    accepted = 0
    already_applied = 0
    conflicts = 0

    cur = conn.cursor()
    with open(file_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            op = obj.get("operation")
            table = obj.get("table")
            data = obj.get("data") or {}

            if table == "maintenance":
                maint_id = data.get("id")
                if op == "delete":
                    if not maint_id:
                        conflicts += 1
                        continue
                    cur.execute(
                        "SELECT substation_id FROM maintenance WHERE id=?", (maint_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        already_applied += 1
                        continue
                    substation_id = (
                        row[0]
                        if isinstance(row, (tuple, list))
                        else row["substation_id"]
                    )
                    cur.execute(
                        "SELECT element_id FROM maintenance_elements "
                        "WHERE maintenance_id=?",
                        (maint_id,),
                    )
                    affected_elements = [
                        r[0] if isinstance(r, (tuple, list)) else r["element_id"]
                        for r in (cur.fetchall() or [])
                    ]
                    try:
                        from onedrive_hybrid_storage import delete_maintenance_folders

                        delete_maintenance_folders(conn, maint_id)
                    except Exception:
                        pass
                    cur.execute(
                        "DELETE FROM maintenance_people WHERE maintenance_id=?",
                        (maint_id,),
                    )
                    cur.execute(
                        "DELETE FROM maintenance_elements WHERE maintenance_id=?",
                        (maint_id,),
                    )
                    cur.execute("DELETE FROM maintenance WHERE id=?", (maint_id,))
                    _refresh_maintenance_dates(cur, substation_id, affected_elements)
                    conn.commit()
                    accepted += 1
                    continue

                if op == "update":
                    if not maint_id:
                        conflicts += 1
                        continue
                    cur.execute(
                        "SELECT substation_id FROM maintenance WHERE id=?", (maint_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        op = "insert"
                    else:
                        existing_substation_id = (
                            row[0]
                            if isinstance(row, (tuple, list))
                            else row["substation_id"]
                        )
                        maint_cols = [
                            r[1] for r in cur.execute("PRAGMA table_info(maintenance)")
                        ]
                        update_keys = [
                            k for k in data.keys() if k in maint_cols and k != "id"
                        ]
                        if update_keys:
                            assignments = ",".join([f"{key}=?" for key in update_keys])
                            cur.execute(
                                f"UPDATE maintenance SET {assignments} WHERE id=?",
                                [data[key] for key in update_keys] + [maint_id],
                            )
                        try:
                            from onedrive_hybrid_storage import (
                                invalidate_maintenance_reports,
                                prune_stale_dga_measurements,
                            )

                            invalidate_maintenance_reports(
                                conn, maint_id, delete_files=True
                            )
                        except Exception:
                            pass
                        cur.execute(
                            "SELECT element_id FROM maintenance_elements "
                            "WHERE maintenance_id=?",
                            (maint_id,),
                        )
                        previous_element_ids = [
                            r[0] if isinstance(r, (tuple, list)) else r["element_id"]
                            for r in (cur.fetchall() or [])
                        ]
                        cur.execute(
                            "DELETE FROM maintenance_elements WHERE maintenance_id=?",
                            (maint_id,),
                        )
                        elements = data.get("elements") or []
                        seen_element_ids = set()
                        new_element_ids = []
                        for elem in elements:
                            elem_id = elem.get("element_id") or elem.get("id")
                            elem_comments = elem.get("element_comments") or elem.get(
                                "comments"
                            )
                            if not elem_id or elem_id in seen_element_ids:
                                continue
                            seen_element_ids.add(elem_id)
                            new_element_ids.append(elem_id)
                            cur.execute(
                                "INSERT INTO maintenance_elements "
                                "(maintenance_id, element_id, element_comments) "
                                "VALUES (?, ?, ?)",
                                (maint_id, elem_id, elem_comments),
                            )
                            if data.get("date_time"):
                                cur.execute(
                                    "UPDATE elements SET maintenance_date=? WHERE id=?",
                                    (data.get("date_time"), elem_id),
                                )
                        try:
                            prune_stale_dga_measurements(
                                conn,
                                maintenance_id=maint_id,
                                valid_element_ids=new_element_ids,
                            )
                        except Exception:
                            pass
                        _refresh_maintenance_dates(
                            cur,
                            data.get("substation_id", existing_substation_id),
                            previous_element_ids + new_element_ids,
                        )
                        conn.commit()
                        accepted += 1
                        continue

                if op != "insert":
                    continue

                # Check if maintenance record exists (by id field)
                if maint_id:
                    existence = _record_exists_with_data(
                        cur, "maintenance", maint_id, data
                    )
                    if existence == "identical":
                        already_applied += 1
                        continue
                    elif existence == "different":
                        conflicts += 1
                        continue

                maint_cols = [
                    r[1] for r in cur.execute("PRAGMA table_info(maintenance)")
                ]
                maint_keys = [k for k in data.keys() if k in maint_cols]
                if maint_keys:
                    try:
                        placeholders = ",".join(["?"] * len(maint_keys))
                        columns = ",".join(maint_keys)
                        sql = (
                            f"INSERT INTO maintenance ({columns}) "
                            f"VALUES ({placeholders})"
                        )
                        cur.execute(sql, [data[k] for k in maint_keys])
                        maintenance_id = cur.lastrowid
                    except sqlite3.IntegrityError:
                        conflicts += 1
                        conn.rollback()
                        continue
                else:
                    continue

                # Insert related elements
                elements = data.get("elements") or []
                elements_ok = True
                seen_element_ids = set()
                for elem in elements:
                    elem_id = elem.get("element_id") or elem.get("id")
                    elem_comments = elem.get("element_comments") or elem.get("comments")
                    if not elem_id:
                        continue
                    # Skip duplicate element ids in the same payload line.
                    if elem_id in seen_element_ids:
                        continue
                    seen_element_ids.add(elem_id)
                    try:
                        cur.execute(
                            """
                            INSERT INTO maintenance_elements (
                                maintenance_id,
                                element_id,
                                element_comments
                            )
                            SELECT ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1
                                FROM maintenance_elements
                                WHERE maintenance_id = ? AND element_id = ?
                            )
                            """,
                            (
                                maintenance_id,
                                elem_id,
                                elem_comments,
                                maintenance_id,
                                elem_id,
                            ),
                        )
                        if data.get("date_time") and elem_id:
                            cur.execute(
                                "UPDATE elements SET maintenance_date=? WHERE id=?",
                                (data.get("date_time"), elem_id),
                            )
                    except sqlite3.IntegrityError:
                        elements_ok = False
                        break

                if elements_ok:
                    conn.commit()
                    accepted += 1
                else:
                    conflicts += 1
                    conn.rollback()
                continue

            if table == "isolation_requests":
                result = _apply_isolation_request_change(cur, conn, op, data)
                if result == "accepted":
                    accepted += 1
                elif result == "already_applied":
                    already_applied += 1
                elif result == "conflict":
                    conflicts += 1
                continue

            result = _apply_generic_table_change(cur, conn, table, op, data)
            if result == "accepted":
                accepted += 1
            elif result == "already_applied":
                already_applied += 1
            elif result == "conflict":
                conflicts += 1

    return (accepted, already_applied, conflicts)


def process_sync_inbox(
    conn: sqlite3.Connection,
    sync_root: str,
    actor: str = "desktop",
    progress_callback=None,
) -> dict:
    """
    Process all change files in the sync inbox (idempotent).

    Files are kept in place after processing. Each file is processed every time
    it's encountered, but record-level deduplication prevents duplicate insertions.
    This allows multiple users to "import" the same change file without conflicts.
    """
    tree = ensure_sync_tree(sync_root)
    pending_dir = tree["inbox_pending"]
    accepted_dir = tree["accepted"]
    audit_path = os.path.join(tree["logs"], "sync_events.jsonl")
    tracker_path = os.path.join(tree["logs"], ".processed_files.json")

    # Load existing tracker for reference (but we'll process files regardless)
    tracker = _load_processed_tracker(tracker_path)

    files = []
    # Check both pending and accepted directories
    for item in sorted(os.listdir(pending_dir)):
        src = os.path.join(pending_dir, item)
        if not os.path.isfile(src):
            continue
        if not item.lower().endswith((".json", ".jsonl")):
            continue
        files.append((item, src))

    for item in sorted(os.listdir(accepted_dir)):
        src = os.path.join(accepted_dir, item)
        if not os.path.isfile(src):
            continue
        if not item.lower().endswith((".json", ".jsonl")):
            continue
        # Extract original filename (remove timestamp prefix if present)
        parts = item.split("_", 3)
        if len(parts) >= 4:  # yyyymmdd_hhmmss_ffffff_originalname
            original_name = "_".join(parts[3:])
        else:
            original_name = item
        # Only add if not already processed in this sync cycle
        # (to avoid duplicates from pending and accepted)
        if original_name not in [f[0] for f in files]:
            files.append((original_name, src))

    accepted = 0
    already_applied = 0
    rejected = 0
    conflicts = 0
    file_summaries: list[dict] = []

    for idx, (original_name, src) in enumerate(files):
        # Report per-file progress when a callback is available
        try:
            if progress_callback and len(files) > 0:
                try:
                    progress_callback(
                        operation="Processing incoming changes",
                        substation=None,
                        current=idx + 1,
                        total=len(files),
                    )
                except Exception:
                    pass
        except Exception:
            pass
        payload_summary = _summarize_change_file(src)
        file_summary = {
            "source_file": original_name,
            "entries": int(payload_summary.get("entries", 0) or 0),
            "insert_entries": int(payload_summary.get("insert_entries", 0) or 0),
            "table_counts": payload_summary.get("table_counts", {}),
            "status": "pending",
            "accepted": 0,
            "already_applied": 0,
            "conflicts": 0,
            "rejected": 0,
        }

        event = {
            "timestamp_utc": _utc_now_iso(),
            "actor": actor,
            "source_file": original_name,
            "status": "pending",
        }

        try:
            file_accepted, file_already_applied, file_conflicts = (
                _apply_change_log_to_db(conn, src, tracker, original_name)
            )

            # Determine overall status
            if file_conflicts > 0:
                event["status"] = "conflict"
                event["details"] = {
                    "accepted": file_accepted,
                    "already_applied": file_already_applied,
                    "conflicts": file_conflicts,
                }
                file_summary["status"] = "conflict"
                file_summary["accepted"] = int(file_accepted)
                file_summary["already_applied"] = int(file_already_applied)
                file_summary["conflicts"] = int(file_conflicts)
                conflicts += file_conflicts
                tracker[original_name] = {
                    "status": "conflict",
                    "processed_at": _utc_now_iso(),
                    "processed_by": actor,
                }
            elif file_already_applied == 0 and file_accepted == 0:
                # File had no applicable changes
                event["status"] = "rejected"
                event["reason"] = "No applicable changes found"
                file_summary["status"] = "rejected"
                file_summary["rejected"] = int(
                    file_summary.get("insert_entries", 0) or 0
                )
                rejected += 1
                tracker[original_name] = {
                    "status": "rejected",
                    "processed_at": _utc_now_iso(),
                    "processed_by": actor,
                    "reason": "No applicable changes",
                }
            elif file_already_applied > 0 and file_accepted == 0:
                event["status"] = "already_applied"
                event["count"] = file_already_applied
                file_summary["status"] = "already_applied"
                file_summary["already_applied"] = int(file_already_applied)
                already_applied += file_already_applied
                tracker[original_name] = {
                    "status": "already_applied",
                    "processed_at": _utc_now_iso(),
                    "processed_by": actor,
                    "count": file_already_applied,
                }
            else:
                event["status"] = "accepted"
                event["details"] = {
                    "accepted": file_accepted,
                    "already_applied": file_already_applied,
                    "conflicts": file_conflicts,
                }
                file_summary["status"] = "accepted"
                file_summary["accepted"] = int(file_accepted)
                file_summary["already_applied"] = int(file_already_applied)
                accepted += file_accepted
                tracker[original_name] = {
                    "status": "accepted",
                    "processed_at": _utc_now_iso(),
                    "processed_by": actor,
                    "details": {
                        "accepted": file_accepted,
                        "already_applied": file_already_applied,
                        "conflicts": file_conflicts,
                    },
                }
        except Exception as exc:
            event["status"] = "rejected"
            event["error"] = str(exc)
            file_summary["status"] = "rejected"
            file_summary["rejected"] = int(file_summary.get("insert_entries", 0) or 0)
            rejected += 1
            tracker[original_name] = {
                "status": "rejected",
                "processed_at": _utc_now_iso(),
                "processed_by": actor,
                "error": str(exc),
            }

        _append_jsonl(audit_path, event)
        file_summaries.append(file_summary)

    # Save updated tracker
    _save_processed_tracker(tracker_path, tracker)

    return {
        "processed": len(files),
        "accepted": accepted,
        "already_applied": already_applied,
        "conflicts": conflicts,
        "rejected": rejected,
        "file_summaries": file_summaries,
        "sync_root": sync_root,
        "audit_log": audit_path,
        "tracker": tracker_path,
    }


def prune_old_sync_change_files(sync_root: str, *, max_age_days: int = 60) -> dict:
    """Delete old sync payload files from shared OneDrive folders.

    Files older than `max_age_days` are removed from:
    - inbox/pending
    - inbox/processed/accepted
    - inbox/processed/rejected
    - inbox/processed/conflicts
    """
    tree = ensure_sync_tree(sync_root)
    dirs = [
        tree["inbox_pending"],
        tree["accepted"],
        tree["rejected"],
        tree["conflicts"],
    ]

    max_age_days = max(1, int(max_age_days))
    cutoff_ts = time.time() - float(max_age_days * 24 * 60 * 60)

    removed = 0
    scanned = 0
    errors = 0

    for folder in dirs:
        try:
            names = os.listdir(folder)
        except Exception:
            continue

        for name in names:
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            if not name.lower().endswith((".json", ".jsonl")):
                continue

            scanned += 1
            try:
                mtime = os.path.getmtime(path)
            except Exception:
                errors += 1
                continue

            if mtime >= cutoff_ts:
                continue

            try:
                os.remove(path)
                removed += 1
            except Exception:
                errors += 1

    return {
        "enabled": True,
        "max_age_days": max_age_days,
        "scanned": scanned,
        "removed": removed,
        "errors": errors,
    }


def ensure_backup_tree(backup_root: str) -> dict[str, str]:
    paths = {
        "hot": os.path.join(backup_root, "hot"),
        "daily": os.path.join(backup_root, "daily"),
        "weekly": os.path.join(backup_root, "weekly"),
        "monthly": os.path.join(backup_root, "monthly"),
        "logs": os.path.join(backup_root, "logs"),
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths


def _sqlite_snapshot(db_path: str, output_path: str) -> None:
    tmp = None
    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(db_path, timeout=30)
        fd, tmp = tempfile.mkstemp(suffix=".sqlite", prefix="snapshot_")
        os.close(fd)
        dst_conn = sqlite3.connect(tmp)
        src_conn.backup(dst_conn)
        dst_conn.commit()
        dst_conn.close()
        dst_conn = None
        src_conn.close()
        src_conn = None
        _safe_move(tmp, output_path)
        tmp = None
    finally:
        if dst_conn is not None:
            dst_conn.close()
        if src_conn is not None:
            src_conn.close()
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def create_snapshot(
    db_path: str, backup_root: str, reason: str = "scheduled", tier: str = "hot"
) -> str:
    tree = ensure_backup_tree(backup_root)
    if tier not in tree:
        tier = "hot"
    db_name = Path(db_path).stem
    snapshot_name = f"{db_name}_{_timestamp_slug()}.sqlite"
    out_path = os.path.join(tree[tier], snapshot_name)
    _sqlite_snapshot(db_path, out_path)

    manifest = {
        "timestamp_utc": _utc_now_iso(),
        "db_path": os.path.abspath(db_path),
        "snapshot_path": os.path.abspath(out_path),
        "tier": tier,
        "reason": reason,
    }
    _append_jsonl(os.path.join(tree["logs"], "backup_manifest.jsonl"), manifest)
    return out_path


def _list_backup_files(backup_root: str, tier: str) -> list[str]:
    tree = ensure_backup_tree(backup_root)
    tier_dir = tree.get(tier, tree["hot"])
    files = [
        os.path.join(tier_dir, name)
        for name in os.listdir(tier_dir)
        if name.lower().endswith(".sqlite")
        and os.path.isfile(os.path.join(tier_dir, name))
    ]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def prune_backup_tier(backup_root: str, tier: str, keep: int) -> list[str]:
    files = _list_backup_files(backup_root, tier)

    removed = []
    for old_path in files[keep:]:
        try:
            os.remove(old_path)
            removed.append(old_path)
        except Exception:
            pass
    return removed


def prune_hot_backups(backup_root: str, keep: int = 3) -> list[str]:
    return prune_backup_tier(backup_root, "hot", keep)


def _backup_slot_slug(tier: str, now: datetime | None = None) -> str:
    current = now or datetime.now()
    if tier == "daily":
        return current.strftime("%Y%m%d")
    if tier == "weekly":
        iso_year, iso_week, _ = current.isocalendar()
        return f"{iso_year}W{iso_week:02d}"
    if tier == "monthly":
        return current.strftime("%Y%m")
    return _timestamp_slug()


def _periodic_snapshot_name(db_path: str, tier: str, slot_slug: str) -> str:
    db_name = Path(db_path).stem
    return f"{db_name}_{tier}_{slot_slug}.sqlite"


def _copy_snapshot(src_path: str, dst_path: str) -> None:
    fd, tmp = tempfile.mkstemp(suffix=".sqlite", prefix="backup_copy_")
    os.close(fd)
    try:
        shutil.copy2(src_path, tmp)
        _safe_move(tmp, dst_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def refresh_periodic_backup(
    db_path: str,
    source_snapshot_path: str,
    backup_root: str,
    tier: str,
    reason: str = "scheduled",
    now: datetime | None = None,
) -> str | None:
    if tier not in {"daily", "weekly", "monthly"}:
        return None

    tree = ensure_backup_tree(backup_root)
    slot_slug = _backup_slot_slug(tier, now=now)
    out_path = os.path.join(
        tree[tier], _periodic_snapshot_name(db_path, tier, slot_slug)
    )
    _copy_snapshot(source_snapshot_path, out_path)
    _append_jsonl(
        os.path.join(tree["logs"], "backup_manifest.jsonl"),
        {
            "timestamp_utc": _utc_now_iso(),
            "db_path": os.path.abspath(db_path),
            "snapshot_path": os.path.abspath(out_path),
            "tier": tier,
            "reason": reason,
        },
    )
    return out_path


def maintain_backup_set(
    db_path: str,
    backup_root: str,
    reason: str = "scheduled",
    hot_keep: int = 3,
    now: datetime | None = None,
) -> dict:
    hot_snapshot = create_snapshot(db_path, backup_root, reason=reason, tier="hot")

    created = {"hot": hot_snapshot}
    removed = {
        "hot": prune_hot_backups(backup_root, keep=max(1, int(hot_keep))),
    }

    for tier in ("daily", "weekly", "monthly"):
        created[tier] = refresh_periodic_backup(
            db_path,
            hot_snapshot,
            backup_root,
            tier=tier,
            reason=reason,
            now=now,
        )
        removed[tier] = prune_backup_tier(
            backup_root,
            tier,
            keep=BACKUP_TIER_KEEP_DEFAULTS[tier],
        )

    return {
        "created": created,
        "removed": removed,
        "backup_root": backup_root,
    }


def list_backups(
    backup_root: str,
    tiers: tuple[str, ...] | None = None,
    limit_per_tier: int | None = None,
) -> list[dict]:
    tiers = tiers or BACKUP_TIER_ORDER
    backups = []
    for tier in tiers:
        tier_files = _list_backup_files(backup_root, tier)
        if limit_per_tier is not None:
            tier_files = tier_files[:limit_per_tier]
        for path in tier_files:
            try:
                backups.append(
                    {
                        "tier": tier,
                        "name": os.path.basename(path),
                        "path": path,
                        "size": os.path.getsize(path),
                        "mtime": os.path.getmtime(path),
                    }
                )
            except Exception:
                pass
    return backups


def run_sync_cycle(
    conn: sqlite3.Connection,
    db_path: str | None = None,
    sync_root: str | None = None,
    backup_root: str | None = None,
    actor: str = "desktop",
    create_backup_on_change: bool = True,
    hot_keep: int = 3,
    progress_callback=None,
) -> dict:
    effective_db = resolve_db_path(db_path)
    effective_sync_root = sync_root or resolve_sync_root(effective_db)
    effective_backup_root = backup_root or resolve_backup_root(effective_db)

    sync_summary = process_sync_inbox(
        conn, effective_sync_root, actor=actor, progress_callback=progress_callback
    )

    retention_enabled = bool(get_app_setting("sync_retention_enabled", True))
    retention_days = int(get_app_setting("sync_retention_days", 60) or 60)
    retention_summary = {
        "enabled": retention_enabled,
        "max_age_days": max(1, retention_days),
        "scanned": 0,
        "removed": 0,
        "errors": 0,
    }

    if retention_enabled:
        retention_summary = prune_old_sync_change_files(
            effective_sync_root,
            max_age_days=max(1, retention_days),
        )

    snapshot_path = None
    if create_backup_on_change and sync_summary["accepted"] > 0:
        backup_summary = maintain_backup_set(
            effective_db,
            effective_backup_root,
            reason=f"sync_accepted:{sync_summary['accepted']}",
            hot_keep=max(1, int(hot_keep)),
        )
        snapshot_path = backup_summary["created"]["hot"]

    return {
        "sync": sync_summary,
        "retention": retention_summary,
        "snapshot": snapshot_path,
        "backup_root": effective_backup_root,
    }
