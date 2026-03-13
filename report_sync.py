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
from pathlib import Path
from datetime import datetime


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
            "SELECT element_type, name FROM elements WHERE id = ?",
            (element_id,)
        )
        element_row = cursor.fetchone()
        if not element_row:
            return {
                "error": f"Element {element_id} not found",
                "path": None,
                "action": None,
            }
        
        elem_type, elem_name = element_row
        safe_name = elem_name.replace("/", "-").replace("\\", "-").replace(":", "-")
        
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
            _report_subfolder_name_for_element(elem_type)
        )
        
        # Get substation name for new naming convention
        cursor.execute(
            "SELECT s.name FROM elements e "
            "JOIN substations s ON e.substation_id = s.id "
            "WHERE e.id = ?",
            (element_id,)
        )
        substation_row = cursor.fetchone()
        substation_name = substation_row[0] if substation_row and isinstance(substation_row, (tuple, list)) else (substation_row["name"] if substation_row else "unknown")
        safe_substation = substation_name.replace("/", "-").replace("\\", "-").replace(":", "-")
        
        # Construct canonical filename
        canonical_path = os.path.join(
            subfolder,
            _canonical_report_filename(substation_name, elem_name, maintenance_id),
        )
        
        # Check if file exists in database (should exist in shared folder)
        existing_db_path = get_maintenance_report_path(
            conn,
            maintenance_id=maintenance_id,
            element_id=element_id,
            report_type="pdf",
            verify_exists=False,
        )
        
        file_exists = os.path.exists(_fs_path(canonical_path))
        db_path_matches = existing_db_path == canonical_path
        
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


def safe_generate_and_store_report(
    conn,
    *,
    maintenance_id: int,
    element_id: int,
    gate_value: str | None = None,
    db_path: str | None = None,
    user_prompted_action: str | None = None,
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
        if file_exists and user_prompted_action is None:
            return {
                "success": False,
                "path": report_path,
                "exists": True,
                "message": f"Report already exists at:\n{report_path}\n\nΕπιλέξτε: Αντικατάσταση, Άνοιγμα ή Ακύρωση",
                "action_taken": "prompt_user",
            }
        
        # Determine what to do
        action = user_prompted_action or ("replace" if file_exists else "create")
        
        if action == "open":
            # Just return the existing path
            return {
                "success": True,
                "path": report_path,
                "message": f"Opening existing report...",
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
                "message": f"Report generation completed but file not found at:\n{generated_path}",
                "action_taken": "error",
            }
        
        # Get file size as verification
        file_size = os.path.getsize(_fs_path(generated_path))
        if file_size < 1000:  # Less than 1KB is suspicious
            return {
                "success": False,
                "path": None,
                "message": f"Report file is suspiciously small ({file_size} bytes).\nGeneration may have failed.",
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
            "message": f"Report successfully {action_msg}.\nFile: {generated_path}\nSize: {file_size} bytes",
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
    # Ensure row factory is set
    original_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as cnt FROM maintenance_report_paths")
    total_tracked = cursor.fetchone()["cnt"]
    
    cursor.execute("""
        SELECT maintenance_id, element_id, report_path
        FROM maintenance_report_paths
        WHERE report_type = 'pdf'
    """)
    
    report_rows = cursor.fetchall()
    existing = 0
    missing = 0
    missing_reports = []
    
    for row in report_rows:
        m_id, e_id, path = row["maintenance_id"], row["element_id"], row["report_path"]
        if os.path.exists(path):
            existing += 1
        else:
            missing += 1
            missing_reports.append((m_id, e_id, path))
    
    # Restore original row_factory
    conn.row_factory = original_row_factory
    
    return {
        "total_tracked": total_tracked,
        "existing_files": existing,
        "missing_files": missing,
        "missing_details": missing_reports[:10],  # First 10 for summary
        "status": "OK" if missing == 0 else f"WARN: {missing} missing reports",
    }
