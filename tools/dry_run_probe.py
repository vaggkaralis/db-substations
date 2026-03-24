#!/usr/bin/env python3
"""Dry-run probe: compute startup sync probe and compare with persisted state.
Does not modify DB or perform sync; read-only.
"""
import os, json, time
from datetime import datetime
from sync_service import resolve_sync_root
from onedrive_hybrid_storage import resolve_shared_root
from config_manager import get_app_setting

def scan_sync_payload_dir(dir_path):
    count = 0
    latest = 0.0
    try:
        for name in os.listdir(dir_path):
            fp = os.path.join(dir_path, name)
            if not os.path.isfile(fp):
                continue
            if not name.lower().endswith((".json", ".jsonl")):
                continue
            count += 1
            try:
                mt = os.path.getmtime(fp)
                if mt > latest:
                    latest = mt
            except Exception:
                pass
    except Exception:
        pass
    return {"count": int(count), "latest_mtime": round(float(latest), 3)}


def scan_actionable_pending(pending_dir, tracker_path):
    # Load tracker
    tracker = {}
    try:
        with open(tracker_path, "r", encoding="utf-8") as fh:
            tracker = json.load(fh) or {}
    except Exception:
        tracker = {}
    actionable_count = 0
    latest = 0.0
    try:
        for name in sorted(os.listdir(pending_dir)):
            if not name.lower().endswith((".json", ".jsonl")):
                continue
            fp = os.path.join(pending_dir, name)
            if not os.path.isfile(fp):
                continue
            # Determine original name
            orig = name
            parts = name.split("_", 3)
            if len(parts) >= 4:
                orig = "_".join(parts[3:])
            status = (tracker.get(orig) or {}).get("status") if isinstance(tracker, dict) else None
            if not status or str(status).strip().lower() in {"", "pending", "conflict"}:
                actionable_count += 1
            try:
                mt = os.path.getmtime(fp)
                if mt > latest:
                    latest = mt
            except Exception:
                pass
    except Exception:
        pass
    return {"count": int(actionable_count), "latest_mtime": round(float(latest), 3)}


def compute_probe(db_path):
    sync_root = resolve_sync_root(db_path)
    pending_dir = os.path.join(sync_root, "inbox", "pending")
    accepted_dir = os.path.join(sync_root, "inbox", "processed", "accepted")
    tracker_path = os.path.join(sync_root, "logs", ".processed_files.json")
    shared_root = resolve_shared_root(db_path)
    try:
        db_mtime = round(float(os.path.getmtime(db_path)), 3)
    except Exception:
        db_mtime = 0.0
    try:
        tracker_mtime = round(float(os.path.getmtime(tracker_path)), 3)
    except Exception:
        tracker_mtime = 0.0
    shared_exists = os.path.isdir(shared_root)
    try:
        shared_mtime = round(float(os.path.getmtime(shared_root)), 3) if shared_exists else 0.0
    except Exception:
        shared_mtime = 0.0
    shared_substation_dirs = 0
    if shared_exists:
        try:
            shared_substation_dirs = sum(1 for name in os.listdir(shared_root) if os.path.isdir(os.path.join(shared_root, name)) and not name.startswith("_"))
        except Exception:
            shared_substation_dirs = 0
    pending_total = scan_sync_payload_dir(pending_dir)
    pending_actionable = scan_actionable_pending(pending_dir, tracker_path)
    accepted = scan_sync_payload_dir(accepted_dir)
    return {
        "version": 1,
        "db_path": os.path.abspath(db_path),
        "sync_root": os.path.abspath(sync_root),
        "shared_root": os.path.abspath(shared_root),
        "shared_root_exists": bool(shared_exists),
        "shared_root_mtime": shared_mtime,
        "shared_substation_dirs": int(shared_substation_dirs),
        "db_mtime": db_mtime,
        "pending": pending_actionable,
        "pending_total": pending_total,
        "accepted": accepted,
        "tracker_mtime": tracker_mtime,
    }


def load_saved_state(db_path):
    db_dir = os.path.dirname(os.path.abspath(db_path))
    path = os.path.join(db_dir, ".startup_sync_state.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def main():
    # Find DB path from app settings or default
    from config_manager import get_db_path, get_app_setting
    db_path = get_db_path() or os.path.join(os.getcwd(), "substations.db")
    minutes = int(get_app_setting("sync_auto_cycle_minutes", 15) or 15)
    print(f"Using sync_auto_cycle_minutes = {minutes}")
    probe = compute_probe(db_path)
    print("Computed probe:")
    print(json.dumps(probe, indent=2, ensure_ascii=False))
    saved = load_saved_state(db_path)
    if not saved:
        print("No saved startup probe state found (first run).")
        return
    previous = saved.get("last_probe") or {}
    # Simple actionable detection (mimic app): compare pending counts and latest mtimes
    prev_pending = int(((previous.get("pending") or {}).get("count", 0) or 0))
    curr_pending = int(((probe.get("pending") or {}).get("count", 0) or 0))
    prev_pending_latest = float(((previous.get("pending") or {}).get("latest_mtime", 0.0) or 0.0))
    curr_pending_latest = float(((probe.get("pending") or {}).get("latest_mtime", 0.0) or 0.0))
    actionable = False
    reasons = []
    if prev_pending != curr_pending:
        actionable = True
        reasons.append(f"pending count changed: {prev_pending} -> {curr_pending}")
    if prev_pending_latest != curr_pending_latest:
        actionable = True
        reasons.append(f"pending latest mtime changed: {datetime.fromtimestamp(prev_pending_latest) if prev_pending_latest else prev_pending_latest} -> {datetime.fromtimestamp(curr_pending_latest) if curr_pending_latest else curr_pending_latest}")
    if not probe.get("shared_root_exists", True):
        actionable = True
        reasons.append("shared root missing")
    print("Probe actionable:" , actionable)
    if reasons:
        print("Reasons:")
        for r in reasons:
            print(" - ", r)

if __name__ == '__main__':
    main()
