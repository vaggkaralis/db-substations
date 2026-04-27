"""
Report generation and synchronization management.

Handles:
- Smart report folder creation (on-demand, prevents empty folders)
- Existing report detection and user prompts
- Synchronization verification
- Database tracking of generated reports
"""

import os
import sqlite3
import hashlib

from pdf_reports import repair_pdf_access


def _fs_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def get_or_prompt_report_path(
    conn,
    *,
    maintenance_id: int,
    element_id: int,
    gate_value: str | None = None,
    db_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Get the proper report path for a maintenance report, handling existing reports.

    Returns dict with:
        - path: The target file path for the report
        - action: 'create' (new), 'replace' (overwrite), 'open' (use existing)
        - exists: Whether the path currently has a file
        - shared_root: The OneDrive shared folder root

    If file exists, caller should prompt user about the action to take.
    """
    from onedrive_hybrid_storage import (
        get_transformer_report_targets,
        get_maintenance_report_path,
        resolve_shared_root,
        _report_subfolder_name_for_element,
        _canonical_report_filename,
    )

    try:
        # Get element type for subfolder determination
        cursor = conn.cursor()
        cursor.execute(
            "SELECT element_type, name, breaker_category FROM elements WHERE id = ?",
            (element_id,),
        )
        element_row = cursor.fetchone()
        if not element_row:
            return {
                "error": f"Element {element_id} not found",
                "path": None,
                "action": None,
            }

        elem_type, elem_name = (
            (element_row[0], element_row[1])
            if isinstance(element_row, (tuple, list))
            else (element_row["element_type"], element_row["name"])
        )
        breaker_category = (
            element_row[2]
            if isinstance(element_row, (tuple, list))
            else element_row["breaker_category"]
        )
        # Get the proper report target folder from storage layer
        targets = get_transformer_report_targets(
            conn,
            maintenance_id=maintenance_id,
            gate_value=gate_value,
            db_path=db_path,
        )

        if not targets:
            return {
                "error": f"No report targets found for maintenance {maintenance_id}",
                "path": None,
                "action": None,
            }

        # Use first target (should typically be only one)
        reports_root = targets[0]

        # Get element-specific subfolder
        subfolder = os.path.join(
            reports_root,
            _report_subfolder_name_for_element(elem_type, breaker_category),
        )

        # Get substation name for new naming convention
        cursor.execute(
            "SELECT s.name FROM elements e "
            "JOIN substations s ON e.substation_id = s.id "
            "WHERE e.id = ?",
            (element_id,),
        )
        substation_row = cursor.fetchone()
        substation_name = (
            substation_row[0]
            if substation_row and isinstance(substation_row, (tuple, list))
            else (substation_row["name"] if substation_row else "unknown")
        )
        # Construct canonical filename
        canonical_path = os.path.join(
            subfolder,
            _canonical_report_filename(
                substation_name,
                elem_name,
                maintenance_id,
                parent_dir=subfolder,
            ),
        )

        # Check if file exists in database (should exist in shared folder)
        existing_db_path = get_maintenance_report_path(
            conn,
            maintenance_id=maintenance_id,
            element_id=element_id,
            report_type="pdf",
            verify_exists=False,
        )

        file_exists = repair_pdf_access(canonical_path)
        shared_root = resolve_shared_root(db_path)

        return {
            "path": canonical_path,
            "subfolder": subfolder,
            "action": "replace" if file_exists else "create",
            "exists": file_exists,
            "db_tracked": bool(existing_db_path),
            "shared_root": shared_root,
            "error": None,
        }

    except Exception as e:
        return {
            "error": str(e),
            "path": None,
            "action": None,
        }


def ensure_maintenance_overview_reports(
    conn,
    *,
    maintenance_id: int,
    db_path: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Ensure maintenance-level overview PDF exists in each reports root."""
    from onedrive_hybrid_storage import (
        _canonical_overview_report_filename,
        get_maintenance_overview_targets,
        get_maintenance_overview_report_path,
        upsert_maintenance_overview_report_path,
    )
    from pdf_reports import generate_maintenance_overview_report as gen_overview_report

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id, s.name
        FROM maintenance m
        JOIN substations s ON s.id = m.substation_id
        WHERE m.id = ?
        """,
        (maintenance_id,),
    )
    row = cursor.fetchone()
    if not row:
        return {
            "generated": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [f"Maintenance {maintenance_id} not found"],
        }

    substation_name = row[1] if isinstance(row, (tuple, list)) else row["name"]
    targets = get_maintenance_overview_targets(
        conn, maintenance_id=maintenance_id, db_path=db_path
    )

    generated = 0
    updated = 0
    skipped = 0
    errors = []

    for target in targets:
        gate_key = target["gate_key"]
        reports_root = target["reports_root"]
        path = os.path.join(
            reports_root,
            _canonical_overview_report_filename(
                substation_name,
                maintenance_id,
                parent_dir=reports_root,
            ),
        )
        tracked = get_maintenance_overview_report_path(
            conn,
            maintenance_id=maintenance_id,
            gate_key=gate_key,
            verify_exists=False,
        )
        file_exists = repair_pdf_access(path)

        if file_exists and not overwrite:
            upsert_maintenance_overview_report_path(
                conn,
                maintenance_id=maintenance_id,
                gate_key=gate_key,
                report_path=path,
            )
            skipped += 1
            continue

        try:
            os.makedirs(_fs_path(reports_root), exist_ok=True)
            generated_path = gen_overview_report(conn, maintenance_id, output_path=path)
            if not os.path.exists(_fs_path(generated_path)):
                raise FileNotFoundError(generated_path)
            if os.path.getsize(_fs_path(generated_path)) < 1000:
                raise RuntimeError(f"Overview PDF too small: {generated_path}")
            upsert_maintenance_overview_report_path(
                conn,
                maintenance_id=maintenance_id,
                gate_key=gate_key,
                report_path=generated_path,
            )
            if tracked:
                updated += 1
            else:
                generated += 1
        except Exception as exc:
            errors.append(f"maintenance {maintenance_id} gate {gate_key}: {exc}")

    conn.commit()
    return {
        "generated": generated,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:20],
    }


def verify_maintenance_overview_report_synchronization(
    conn, *, db_path: str | None = None
) -> dict:
    """Check whether maintenance overview PDFs exist for each reports root."""
    from onedrive_hybrid_storage import (
        _canonical_overview_report_filename,
        get_maintenance_overview_report_path,
        get_maintenance_overview_targets,
    )

    original_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id AS maintenance_id, s.name AS substation_name
            FROM maintenance m
            JOIN substations s ON s.id = m.substation_id
            ORDER BY m.id DESC
            """)
        rows = cursor.fetchall() or []

        existing = 0
        missing = 0
        stale_tracked = 0
        missing_details = []

        for row in rows:
            maintenance_id = row["maintenance_id"]
            substation_name = row["substation_name"]
            targets = get_maintenance_overview_targets(
                conn,
                maintenance_id=maintenance_id,
                db_path=db_path,
            )
            for target in targets:
                gate_key = target["gate_key"]
                reports_root = target["reports_root"]
                tracked_path = get_maintenance_overview_report_path(
                    conn,
                    maintenance_id=maintenance_id,
                    gate_key=gate_key,
                    verify_exists=False,
                )
                canonical_path = os.path.join(
                    reports_root,
                    _canonical_overview_report_filename(
                        substation_name,
                        maintenance_id,
                        parent_dir=reports_root,
                    ),
                )

                if tracked_path and repair_pdf_access(tracked_path):
                    existing += 1
                    continue
                if repair_pdf_access(canonical_path):
                    existing += 1
                    if tracked_path and tracked_path != canonical_path:
                        stale_tracked += 1
                    continue

                missing += 1
                missing_details.append(
                    (maintenance_id, gate_key, tracked_path or canonical_path)
                )

        return {
            "existing_files": existing,
            "missing_files": missing,
            "stale_tracked_rows": stale_tracked,
            "missing_details": missing_details[:10],
            "status": (
                "OK" if missing == 0 else f"WARN: {missing} missing overview reports"
            ),
        }
    finally:
        conn.row_factory = original_row_factory


def safe_generate_and_store_report(
    conn,
    *,
    maintenance_id: int,
    element_id: int,
    gate_value: str | None = None,
    db_path: str | None = None,
    user_prompted_action: str | None = None,
    allow_existing_without_prompt: bool = False,
    ensure_overview: bool = True,
) -> dict:
    """
    Generate a maintenance report and store path in database.

    Args:
        conn: Database connection
        maintenance_id: Maintenance record ID
        element_id: Element ID
        gate_value: Optional gate for report targeting
        db_path: Optional database path
        user_prompted_action: 'create', 'replace', or 'open' from user prompt

    Returns:
        {
            'success': bool,
            'path': str or None,
            'message': str,
            'action_taken': 'created', 'replaced', 'opened', or 'error'
        }
    """
    from onedrive_hybrid_storage import upsert_maintenance_report_path
    from pdf_reports import generate_maintenance_report as gen_report

    try:
        # Get the proper path for this report
        path_info = get_or_prompt_report_path(
            conn,
            maintenance_id=maintenance_id,
            element_id=element_id,
            gate_value=gate_value,
            db_path=db_path,
        )

        if path_info.get("error"):
            return {
                "success": False,
                "path": None,
                "message": f"Error determining report path: {path_info['error']}",
                "action_taken": "error",
            }

        report_path = path_info["path"]
        file_exists = path_info["exists"]
        subfolder = path_info["subfolder"]

        # If file exists and user didn't choose action, return info for caller to prompt
        if (
            file_exists
            and user_prompted_action is None
            and not allow_existing_without_prompt
        ):
            return {
                "success": False,
                "path": report_path,
                "exists": True,
                "message": (
                    f"Report already exists at:\n{report_path}\n\n"
                    "Επιλέξτε: Αντικατάσταση, Άνοιγμα ή Ακύρωση"
                ),
                "action_taken": "prompt_user",
            }

        # Determine what to do
        action = user_prompted_action or ("replace" if file_exists else "create")

        if file_exists and allow_existing_without_prompt:
            try:
                upsert_maintenance_report_path(
                    conn,
                    maintenance_id=maintenance_id,
                    element_id=element_id,
                    report_type="pdf",
                    report_path=report_path,
                )
                if ensure_overview:
                    ensure_maintenance_overview_reports(
                        conn,
                        maintenance_id=maintenance_id,
                        db_path=db_path,
                        overwrite=False,
                    )
                conn.commit()
                return {
                    "success": True,
                    "path": report_path,
                    "message": f"Existing report registered at {report_path}",
                    "action_taken": "tracked_existing",
                }
            except Exception as e:
                return {
                    "success": False,
                    "path": report_path,
                    "message": f"Failed to register existing report:\n{str(e)}",
                    "action_taken": "error",
                }

        if action == "open":
            # Just return the existing path
            return {
                "success": True,
                "path": report_path,
                "message": "Opening existing report...",
                "action_taken": "opened",
            }

        # Create folder only when we're actually generating a report
        try:
            os.makedirs(_fs_path(subfolder), exist_ok=True)
        except Exception as e:
            return {
                "success": False,
                "path": None,
                "message": f"Failed to create report folder:\n{str(e)}",
                "action_taken": "error",
            }

        # Generate the report using the proper output path
        try:
            generated_path = gen_report(
                conn,
                maintenance_id,
                element_id,
                output_path=report_path,
            )
        except Exception as e:
            return {
                "success": False,
                "path": None,
                "message": f"Failed to generate PDF:\n{str(e)}",
                "action_taken": "error",
            }

        # Verify file was actually created
        if not os.path.exists(_fs_path(generated_path)):
            return {
                "success": False,
                "path": None,
                "message": (
                    "Report generation completed but file not found at:\n"
                    f"{generated_path}"
                ),
                "action_taken": "error",
            }

        # Get file size as verification
        file_size = os.path.getsize(_fs_path(generated_path))
        if file_size < 1000:  # Less than 1KB is suspicious
            return {
                "success": False,
                "path": None,
                "message": (
                    f"Report file is suspiciously small ({file_size} bytes).\n"
                    "Generation may have failed."
                ),
                "action_taken": "error",
            }

        # Store path in database for tracking
        try:
            upsert_maintenance_report_path(
                conn,
                maintenance_id=maintenance_id,
                element_id=element_id,
                report_type="pdf",
                report_path=generated_path,
            )
            if ensure_overview:
                ensure_maintenance_overview_reports(
                    conn,
                    maintenance_id=maintenance_id,
                    db_path=db_path,
                    overwrite=True,
                )
            conn.commit()
        except Exception as e:
            return {
                "success": False,
                "path": generated_path,
                "message": f"Report created but failed to update database:\n{str(e)}",
                "action_taken": "error",
            }

        action_msg = "replaced" if action == "replace" else "created"
        return {
            "success": True,
            "path": generated_path,
            "message": (
                f"Report successfully {action_msg}.\n"
                f"File: {generated_path}\n"
                f"Size: {file_size} bytes"
            ),
            "action_taken": action_msg,
        }

    except Exception as e:
        return {
            "success": False,
            "path": None,
            "message": f"Unexpected error during report generation:\n{str(e)}",
            "action_taken": "error",
        }


def verify_report_synchronization(conn, *, db_path: str | None = None) -> dict:
    """
    Verify that all tracked reports exist and are properly synchronized.

    Returns summary of:
    - Total tracked reports
    - Reports that exist on disk
    - Reports that are missing
    - Empty folders that should be cleaned up
    """
    from onedrive_hybrid_storage import (
        get_transformer_report_targets,
        _report_subfolder_name_for_element,
        _canonical_report_filename,
    )

    original_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM maintenance_report_paths
            WHERE report_type = 'pdf'
            """)
        total_tracked = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM maintenance_report_paths mrp
            LEFT JOIN maintenance_elements me
                            ON me.maintenance_id = mrp.maintenance_id
                            AND me.element_id = mrp.element_id
            WHERE mrp.report_type = 'pdf' AND me.maintenance_id IS NULL
            """)
        orphan_tracked = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT DISTINCT
                m.id as maintenance_id,
                me.element_id,
                e.name as element_name,
                e.gate,
                e.element_type,
                e.breaker_category,
                s.name as substation_name,
                mrp.report_path as tracked_path
            FROM maintenance m
            JOIN maintenance_elements me ON me.maintenance_id = m.id
            JOIN elements e ON e.id = me.element_id
            JOIN substations s ON s.id = m.substation_id
            LEFT JOIN maintenance_report_paths mrp
                            ON mrp.maintenance_id = m.id
                            AND mrp.element_id = me.element_id
                            AND mrp.report_type = 'pdf'
            ORDER BY m.id DESC, me.element_id
            """)
        rows = cursor.fetchall()

        existing = 0
        missing = 0
        stale_tracked = 0
        missing_reports = []

        for row in rows:
            maintenance_id = row["maintenance_id"]
            element_id = row["element_id"]
            tracked_path = row["tracked_path"]
            tracked_exists = bool(tracked_path) and repair_pdf_access(tracked_path)

            if tracked_exists:
                existing += 1
                continue

            targets = get_transformer_report_targets(
                conn,
                maintenance_id=maintenance_id,
                gate_value=row["gate"],
                db_path=db_path,
            )

            canonical_exists = False
            canonical_path = None
            for reports_root in targets[:1]:
                subfolder = os.path.join(
                    reports_root,
                    _report_subfolder_name_for_element(
                        row["element_type"], row["breaker_category"]
                    ),
                )
                canonical_path = os.path.join(
                    subfolder,
                    _canonical_report_filename(
                        row["substation_name"],
                        row["element_name"],
                        maintenance_id,
                        parent_dir=subfolder,
                    ),
                )
                if repair_pdf_access(canonical_path):
                    canonical_exists = True
                    break

                sub_elem_hash = hashlib.sha1(
                    (
                        str(row["substation_name"]) + "|" + str(row["element_name"])
                    ).encode("utf-8")
                ).hexdigest()[:8]
                tight_name = f"M{maintenance_id}_E{element_id}_{sub_elem_hash}.pdf"
                tight_path = os.path.join(subfolder, tight_name)
                if repair_pdf_access(tight_path):
                    canonical_exists = True
                    canonical_path = tight_path
                    break

            if canonical_exists:
                existing += 1
                if tracked_path:
                    stale_tracked += 1
            else:
                missing += 1
                missing_reports.append(
                    (maintenance_id, element_id, tracked_path or canonical_path)
                )

        return {
            "total_tracked": total_tracked,
            "current_pairs": len(rows),
            "existing_files": existing,
            "missing_files": missing,
            "stale_tracked_rows": stale_tracked,
            "orphan_tracked_rows": orphan_tracked,
            "missing_details": missing_reports[:10],
            "status": "OK" if missing == 0 else f"WARN: {missing} missing reports",
        }
    finally:
        conn.row_factory = original_row_factory


def export_missing_reports(
    conn,
    *,
    db_path: str | None = None,
    limit: int | None = None,
    progress_callback=None,
) -> dict:
    """
    Generate and store reports for maintenance-element pairs that are not
    currently tracked in `maintenance_report_paths`. Uses
    `safe_generate_and_store_report` to ensure proper folder creation and DB
    registration.

    Args:
        conn: DB connection
        db_path: optional db path used for shared root resolution
        limit: optional maximum number of reports to generate
        progress_callback: optional callable(operation, current, total)

    Returns summary dict with counts and sample errors.
    """
    from onedrive_hybrid_storage import (
        delete_orphaned_maintenance_report_paths,
        retrofit_shared_root_paths,
    )
    from pdf_reports import generate_maintenance_report as _gen_dummy  # noqa: F401
    from report_sync import (
        ensure_maintenance_overview_reports,
        safe_generate_and_store_report,
    )

    cur = conn.cursor()

    delete_orphaned_maintenance_report_paths(conn)
    retrofit_shared_root_paths(conn, db_path=db_path, dry_run=False)

    # Inspect every maintenance-element pair so a wiped shared folder can be
    # regenerated even when stale DB rows already exist.
    q = """
        SELECT m.id as maintenance_id, me.element_id, e.gate, mrp.report_path
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        JOIN elements e ON e.id = me.element_id
                LEFT JOIN maintenance_report_paths mrp
                    ON mrp.maintenance_id = m.id
                    AND mrp.element_id = me.element_id
                    AND mrp.report_type='pdf'
        ORDER BY m.id
    """
    cur.execute(q)
    rows = cur.fetchall() or []

    total = len(rows)
    if limit:
        rows = rows[:limit]

    generated = 0
    skipped = 0
    errors = []
    touched_maintenance_ids = set()

    for idx, row in enumerate(rows, start=1):
        maintenance_id = (
            row[0] if isinstance(row, (tuple, list)) else row["maintenance_id"]
        )
        element_id = row[1] if isinstance(row, (tuple, list)) else row["element_id"]
        gate_value = row[2] if isinstance(row, (tuple, list)) else row["gate"]
        tracked_path = row[3] if isinstance(row, (tuple, list)) else row["report_path"]

        if tracked_path and repair_pdf_access(tracked_path):
            skipped += 1
            touched_maintenance_ids.add(maintenance_id)
            continue

        if progress_callback and idx % 5 == 0:
            try:
                progress_callback(
                    operation="Exporting reports", current=idx, total=total
                )
            except Exception:
                pass

        try:
            result = safe_generate_and_store_report(
                conn,
                maintenance_id=maintenance_id,
                element_id=element_id,
                gate_value=gate_value,
                db_path=db_path,
                allow_existing_without_prompt=True,
                ensure_overview=False,
            )
            if result.get("success"):
                generated += 1
                touched_maintenance_ids.add(maintenance_id)
            else:
                # If prompting required (existing file), treat as skipped
                if result.get("action_taken") == "prompt_user":
                    skipped += 1
                else:
                    errors.append((maintenance_id, element_id, result.get("message")))
        except Exception as exc:
            errors.append((maintenance_id, element_id, str(exc)))

    all_maintenance_ids = {
        row[0] if isinstance(row, (tuple, list)) else row["maintenance_id"]
        for row in rows
    }

    overview_generated = 0
    overview_errors = []
    for maintenance_id in sorted(all_maintenance_ids):
        try:
            overview_res = ensure_maintenance_overview_reports(
                conn,
                maintenance_id=maintenance_id,
                db_path=db_path,
                overwrite=False,
            )
            overview_generated += overview_res.get("generated", 0) + overview_res.get(
                "updated", 0
            )
            overview_errors.extend(overview_res.get("errors", []))
        except Exception as exc:
            overview_errors.append(f"maintenance {maintenance_id}: {exc}")

    return {
        "total_candidates": total,
        "processed": len(rows),
        "generated": generated,
        "overview_generated": overview_generated,
        "skipped": skipped,
        "errors": (errors + overview_errors)[:20],
    }


def ensure_all_reports_and_prune(
    conn,
    *,
    db_path: str | None = None,
    batch_size: int = 100,
    progress_callback=None,
    dry_run: bool = False,
) -> dict:
    """
    Orchestrate full report export and folder cleanup.

    Steps:
      1. Ensure gate folders for each substation reflect current elements.
      2. Export missing reports in batches using `export_missing_reports`.
      3. Re-run gate sync to prune empty maintenance/gate folders.

    Returns a summary dict with counts and errors.
    """
    from onedrive_hybrid_storage import (
        sync_substation_gate_folders,
        sync_transformer_subelement_folders,
        resolve_shared_root,
    )

    cur = conn.cursor()
    cur.execute("SELECT id FROM substations ORDER BY id")
    subs = [r[0] for r in (cur.fetchall() or [])]

    total_generated = 0
    total_processed = 0
    all_errors = []

    # Step 1: ensure gate folders for all substations (this also prunes empty gates)
    for sid in subs:
        try:
            if not dry_run:
                sync_substation_gate_folders(conn, sid, db_path=db_path)
                sync_transformer_subelement_folders(conn, sid, db_path=db_path)
        except Exception:
            # Non-fatal; continue
            pass

    # Step 2: export missing reports in batches until none remain
    while True:
        try:
            res = export_missing_reports(
                conn,
                db_path=db_path,
                limit=batch_size,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            all_errors.append(str(exc))
            break

        total_processed += res.get("processed", 0)
        total_generated += res.get("generated", 0)
        if res.get("errors"):
            all_errors.extend([str(e) for e in res.get("errors")])

        # Stop when no more candidates processed in this batch
        if res.get("processed", 0) == 0:
            break

        # If running dry_run, only one batch
        if dry_run:
            break

    # Step 3: re-sync to prune any empty folders that may remain
    for sid in subs:
        try:
            if not dry_run:
                sync_substation_gate_folders(conn, sid, db_path=db_path)
                sync_transformer_subelement_folders(conn, sid, db_path=db_path)
        except Exception:
            pass

    shared_root = resolve_shared_root(db_path)

    return {
        "substations_processed": len(subs),
        "total_processed": total_processed,
        "total_generated": total_generated,
        "errors": all_errors[:50],
        "shared_root": shared_root,
    }
