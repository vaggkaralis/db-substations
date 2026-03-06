import json
import os
import sqlite3
import time

from database import init_db
from sync_service import create_snapshot, prune_hot_backups, process_sync_inbox


def _seed_db(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (name, location) VALUES (?, ?)", ("S1", "L1"))
    sub_id = cur.lastrowid
    cur.execute(
        "INSERT INTO elements (substation_id, element_type, name, breaker_category) VALUES (?, ?, ?, ?)",
        (sub_id, "Διακόπτης ΜΤ", "E1", "SF6"),
    )
    elem_id = cur.lastrowid
    conn.commit()
    return sub_id, elem_id


def test_process_sync_inbox_applies_pending_jsonl(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    sub_id, elem_id = _seed_db(conn)

    sync_root = tmp_path / "sync_exchange"
    pending = sync_root / "inbox" / "pending"
    pending.mkdir(parents=True, exist_ok=True)

    payload = {
        "operation": "insert",
        "table": "maintenance",
        "data": {
            "substation_id": sub_id,
            "date_time": "2026-03-06 10:00:00",
            "overall_comments": "From Android",
            "elements": [{"element_id": elem_id, "element_comments": "ok"}],
        },
    }
    entry_path = pending / "entry.jsonl"
    entry_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = process_sync_inbox(conn, str(sync_root), actor="pytest")

    assert summary["processed"] == 1
    assert summary["accepted"] == 1
    assert summary["conflicts"] == 0
    assert summary["rejected"] == 0

    cur = conn.cursor()
    maintenance = cur.execute("SELECT overall_comments FROM maintenance").fetchone()
    assert maintenance is not None
    assert maintenance[0] == "From Android"

    # Verify file stays in pending (idempotent behavior - files not moved)
    pending_files = list(pending.glob("*.jsonl"))
    assert len(pending_files) == 1

    # Verify tracker exists with correct status
    tracker_path = sync_root / "logs" / ".processed_files.json"
    assert tracker_path.exists()
    with open(tracker_path, "r", encoding="utf-8") as f:
        tracker = json.load(f)
    assert "entry.jsonl" in tracker
    assert tracker["entry.jsonl"]["status"] == "accepted"

    audit_log = sync_root / "logs" / "sync_events.jsonl"
    assert audit_log.exists()
    conn.close()


def test_create_snapshot_and_prune_hot(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    _seed_db(conn)
    conn.close()

    backup_root = tmp_path / "backups_auto"

    created = []
    for _ in range(4):
        created.append(create_snapshot(str(db_path), str(backup_root), reason="pytest", tier="hot"))
        time.sleep(0.01)

    removed = prune_hot_backups(str(backup_root), keep=3)
    hot_dir = backup_root / "hot"
    remaining = [p for p in hot_dir.glob("*.sqlite") if p.is_file()]

    assert len(remaining) == 3
    assert len(removed) == 1

    manifest = backup_root / "logs" / "backup_manifest.jsonl"
    assert manifest.exists()
    lines = manifest.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 4
