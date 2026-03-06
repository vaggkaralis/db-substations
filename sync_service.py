import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config_manager import get_app_setting
from settings import DB_PATH


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _safe_move(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)


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
    configured = get_app_setting("backup_root_path", None)
    if configured:
        return os.path.abspath(configured)
    effective_db = resolve_db_path(db_path)
    return os.path.join(os.path.dirname(effective_db), "backups_auto")


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


def _apply_change_log_to_db(conn: sqlite3.Connection, file_path: str) -> None:
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

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

            if op != "insert":
                continue

            if table == "maintenance":
                maint_cols = [r[1] for r in cur.execute("PRAGMA table_info(maintenance)")]
                maint_keys = [k for k in data.keys() if k in maint_cols]
                if maint_keys:
                    placeholders = ",".join(["?"] * len(maint_keys))
                    sql = f"INSERT INTO maintenance ({','.join(maint_keys)}) VALUES ({placeholders})"
                    cur.execute(sql, [data[k] for k in maint_keys])
                    maintenance_id = cur.lastrowid
                else:
                    continue

                elements = data.get("elements") or []
                for elem in elements:
                    elem_id = elem.get("element_id") or elem.get("id")
                    elem_comments = elem.get("element_comments") or elem.get("comments")
                    cur.execute(
                        "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
                        (maintenance_id, elem_id, elem_comments),
                    )
                    if data.get("date_time") and elem_id:
                        cur.execute(
                            "UPDATE elements SET maintenance_date=? WHERE id=?",
                            (data.get("date_time"), elem_id),
                        )
                conn.commit()
                continue

            cols_info = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
            insert_keys = [k for k in data.keys() if k in cols_info]
            if not insert_keys:
                continue
            placeholders = ",".join(["?"] * len(insert_keys))
            sql = f"INSERT INTO {table} ({','.join(insert_keys)}) VALUES ({placeholders})"
            cur.execute(sql, [data[k] for k in insert_keys])
            conn.commit()


def process_sync_inbox(conn: sqlite3.Connection, sync_root: str, actor: str = "desktop") -> dict:
    tree = ensure_sync_tree(sync_root)
    pending_dir = tree["inbox_pending"]
    audit_path = os.path.join(tree["logs"], "sync_events.jsonl")

    files = []
    for item in sorted(os.listdir(pending_dir)):
        src = os.path.join(pending_dir, item)
        if not os.path.isfile(src):
            continue
        if not item.lower().endswith((".json", ".jsonl")):
            continue
        files.append(src)

    accepted = 0
    rejected = 0
    conflicts = 0

    for src in files:
        name = os.path.basename(src)
        stamped_name = f"{_timestamp_slug()}_{name}"
        event = {
            "timestamp_utc": _utc_now_iso(),
            "actor": actor,
            "source_file": name,
            "status": "pending",
        }

        try:
            _apply_change_log_to_db(conn, src)
            dst = os.path.join(tree["accepted"], stamped_name)
            _safe_move(src, dst)
            accepted += 1
            event["status"] = "accepted"
            event["stored_as"] = os.path.basename(dst)
        except sqlite3.IntegrityError as exc:
            dst = os.path.join(tree["conflicts"], stamped_name)
            _safe_move(src, dst)
            conflicts += 1
            event["status"] = "conflict"
            event["error"] = str(exc)
            event["stored_as"] = os.path.basename(dst)
        except Exception as exc:
            dst = os.path.join(tree["rejected"], stamped_name)
            _safe_move(src, dst)
            rejected += 1
            event["status"] = "rejected"
            event["error"] = str(exc)
            event["stored_as"] = os.path.basename(dst)

        _append_jsonl(audit_path, event)

    return {
        "processed": len(files),
        "accepted": accepted,
        "conflicts": conflicts,
        "rejected": rejected,
        "sync_root": sync_root,
        "audit_log": audit_path,
    }


def ensure_backup_tree(backup_root: str) -> dict[str, str]:
    paths = {
        "hot": os.path.join(backup_root, "hot"),
        "daily": os.path.join(backup_root, "daily"),
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


def create_snapshot(db_path: str, backup_root: str, reason: str = "scheduled", tier: str = "hot") -> str:
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


def prune_hot_backups(backup_root: str, keep: int = 3) -> list[str]:
    tree = ensure_backup_tree(backup_root)
    hot_dir = tree["hot"]
    files = [
        os.path.join(hot_dir, name)
        for name in os.listdir(hot_dir)
        if name.lower().endswith(".sqlite") and os.path.isfile(os.path.join(hot_dir, name))
    ]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    removed = []
    for old_path in files[keep:]:
        try:
            os.remove(old_path)
            removed.append(old_path)
        except Exception:
            pass
    return removed


def run_sync_cycle(
    conn: sqlite3.Connection,
    db_path: str | None = None,
    sync_root: str | None = None,
    backup_root: str | None = None,
    actor: str = "desktop",
    create_backup_on_change: bool = True,
    hot_keep: int = 3,
) -> dict:
    effective_db = resolve_db_path(db_path)
    effective_sync_root = sync_root or resolve_sync_root(effective_db)
    effective_backup_root = backup_root or resolve_backup_root(effective_db)

    sync_summary = process_sync_inbox(conn, effective_sync_root, actor=actor)

    snapshot_path = None
    if create_backup_on_change and sync_summary["accepted"] > 0:
        snapshot_path = create_snapshot(
            effective_db,
            effective_backup_root,
            reason=f"sync_accepted:{sync_summary['accepted']}",
            tier="hot",
        )
        prune_hot_backups(effective_backup_root, keep=max(1, int(hot_keep)))

    return {
        "sync": sync_summary,
        "snapshot": snapshot_path,
        "backup_root": effective_backup_root,
    }
