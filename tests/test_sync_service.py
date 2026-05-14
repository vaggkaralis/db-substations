import json
import sqlite3
import time
from datetime import datetime

from database import init_db
from sync_service import (
    _apply_change_log_to_db,
    create_snapshot,
    list_backups,
    maintain_backup_set,
    prune_hot_backups,
    process_sync_inbox,
    resolve_backup_root,
)


def _seed_db(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (name, location) VALUES (?, ?)", ("S1", "L1"))
    sub_id = cur.lastrowid
    cur.execute(
        "INSERT INTO elements (substation_id, element_type, name, breaker_category) "
        "VALUES (?, ?, ?, ?)",
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
    accepted_dir = sync_root / "inbox" / "processed" / "accepted"
    pending.mkdir(parents=True, exist_ok=True)
    local_tracker = tmp_path / "local_tracker.json"

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
    entry_path.write_text(
        json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = process_sync_inbox(
        conn,
        str(sync_root),
        actor="pytest",
        local_tracker_path=str(local_tracker),
    )

    assert summary["processed"] == 1
    assert summary["accepted"] == 1
    assert summary["conflicts"] == 0
    assert summary["rejected"] == 0

    cur = conn.cursor()
    maintenance = cur.execute("SELECT overall_comments FROM maintenance").fetchone()
    assert maintenance is not None
    assert maintenance[0] == "From Android"

    pending_files = list(pending.glob("*.jsonl"))
    archived_files = list(accepted_dir.glob("*.jsonl"))
    assert pending_files == []
    assert len(archived_files) == 1

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


def test_process_sync_inbox_skips_self_origin_payload_and_archives_it(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    sub_id, _elem_id = _seed_db(conn)

    monkeypatch.setattr(
        "sync_service.get_app_setting",
        lambda key, default=None: "device-123" if key == "sync_device_id" else default,
    )
    monkeypatch.setattr("sync_service.set_app_setting", lambda key, value: True)

    sync_root = tmp_path / "sync_exchange"
    pending = sync_root / "inbox" / "pending"
    accepted_dir = sync_root / "inbox" / "processed" / "accepted"
    pending.mkdir(parents=True, exist_ok=True)
    local_tracker = tmp_path / "local_tracker.json"

    payload = {
        "operation": "insert",
        "table": "substations",
        "data": {"id": sub_id, "name": "S1", "location": "L1"},
        "origin_device_id": "device-123",
    }
    entry_path = pending / "self.jsonl"
    entry_path.write_text(
        json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = process_sync_inbox(
        conn,
        str(sync_root),
        actor="pytest",
        local_tracker_path=str(local_tracker),
    )

    assert summary["processed"] == 1
    assert summary["accepted"] == 0
    assert summary["conflicts"] == 0
    assert summary["self_ignored"] == 1
    assert list(pending.glob("*.jsonl")) == []
    assert len(list(accepted_dir.glob("*.jsonl"))) == 1
    assert conn.execute("SELECT COUNT(*) FROM substations").fetchone()[0] == 1
    conn.close()


def test_process_sync_inbox_imports_archived_acceptance_once_per_device(tmp_path):
    source_db = tmp_path / "source.db"
    source_conn = init_db(str(source_db))
    source_sub_id, source_elem_id = _seed_db(source_conn)

    sync_root = tmp_path / "sync_exchange"
    pending = sync_root / "inbox" / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    source_tracker = tmp_path / "source_local_tracker.json"

    payload = {
        "operation": "insert",
        "table": "maintenance",
        "data": {
            "substation_id": source_sub_id,
            "date_time": "2026-03-06 10:00:00",
            "overall_comments": "From Android",
            "elements": [{"element_id": source_elem_id, "element_comments": "ok"}],
        },
    }
    entry_path = pending / "entry.jsonl"
    entry_path.write_text(
        json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    source_summary = process_sync_inbox(
        source_conn,
        str(sync_root),
        actor="pytest-source",
        local_tracker_path=str(source_tracker),
    )
    assert source_summary["accepted"] == 1
    source_conn.close()

    target_db = tmp_path / "target.db"
    target_conn = init_db(str(target_db))
    _seed_db(target_conn)
    target_tracker = tmp_path / "target_local_tracker.json"

    target_summary = process_sync_inbox(
        target_conn,
        str(sync_root),
        actor="pytest-target",
        local_tracker_path=str(target_tracker),
    )
    assert target_summary["processed"] == 1
    assert target_summary["accepted"] == 1

    second_summary = process_sync_inbox(
        target_conn,
        str(sync_root),
        actor="pytest-target",
        local_tracker_path=str(target_tracker),
    )
    assert second_summary["processed"] == 0
    assert second_summary["accepted"] == 0
    assert second_summary["skipped_local"] == 1
    target_conn.close()


def test_process_sync_inbox_fast_archives_pending_files_from_shared_tracker(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    _seed_db(conn)

    sync_root = tmp_path / "sync_exchange"
    pending = sync_root / "inbox" / "pending"
    accepted_dir = sync_root / "inbox" / "processed" / "accepted"
    logs_dir = sync_root / "logs"
    pending.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    local_tracker = tmp_path / "local_tracker.json"

    entry_path = pending / "entry.jsonl"
    entry_path.write_text(
        json.dumps({"operation": "insert", "table": "substations", "data": {"id": 1}})
        + "\n",
        encoding="utf-8",
    )
    tracker_path = logs_dir / ".processed_files.json"
    tracker_path.write_text(
        json.dumps(
            {
                "entry.jsonl": {
                    "status": "accepted",
                    "processed_at": "2026-05-13T08:00:00Z",
                    "processed_by": "pytest",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = process_sync_inbox(
        conn,
        str(sync_root),
        actor="pytest",
        local_tracker_path=str(local_tracker),
    )

    assert summary["processed"] == 0
    assert summary["skipped_local"] == 1
    assert list(pending.glob("*.jsonl")) == []
    assert len(list(accepted_dir.glob("*.jsonl"))) == 1
    conn.close()


def test_create_snapshot_and_prune_hot(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    _seed_db(conn)
    conn.close()

    backup_root = tmp_path / "backups_auto"

    created = []
    for _ in range(4):
        created.append(
            create_snapshot(str(db_path), str(backup_root), reason="pytest", tier="hot")
        )
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


def test_maintain_backup_set_creates_tiered_retention(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    _seed_db(conn)
    conn.close()

    backup_root = tmp_path / "backups_auto"

    summary_1 = maintain_backup_set(
        str(db_path),
        str(backup_root),
        reason="pytest",
        hot_keep=3,
        now=datetime(2026, 5, 9, 9, 0, 0),
    )
    summary_2 = maintain_backup_set(
        str(db_path),
        str(backup_root),
        reason="pytest",
        hot_keep=3,
        now=datetime(2026, 5, 9, 18, 30, 0),
    )
    maintain_backup_set(
        str(db_path),
        str(backup_root),
        reason="pytest",
        hot_keep=3,
        now=datetime(2026, 5, 10, 8, 0, 0),
    )
    maintain_backup_set(
        str(db_path),
        str(backup_root),
        reason="pytest",
        hot_keep=3,
        now=datetime(2026, 5, 18, 8, 0, 0),
    )
    summary_5 = maintain_backup_set(
        str(db_path),
        str(backup_root),
        reason="pytest",
        hot_keep=3,
        now=datetime(2026, 6, 1, 8, 0, 0),
    )

    assert summary_1["created"]["daily"].endswith("main_daily_20260509.sqlite")
    assert summary_2["created"]["daily"].endswith("main_daily_20260509.sqlite")
    assert summary_5["created"]["monthly"].endswith("main_monthly_202606.sqlite")

    hot_files = list((backup_root / "hot").glob("*.sqlite"))
    daily_files = list((backup_root / "daily").glob("*.sqlite"))
    weekly_files = list((backup_root / "weekly").glob("*.sqlite"))
    monthly_files = list((backup_root / "monthly").glob("*.sqlite"))

    assert len(hot_files) == 3
    assert len(daily_files) == 2
    assert len(weekly_files) == 2
    assert len(monthly_files) == 2

    listed = list_backups(str(backup_root), limit_per_tier=5)
    assert {item["tier"] for item in listed} == {"hot", "daily", "weekly", "monthly"}
    assert any(item["name"].endswith("main_daily_20260518.sqlite") for item in listed)
    assert any(item["name"].endswith("main_daily_20260601.sqlite") for item in listed)


def test_resolve_backup_root_uses_db_relative_configured_path(tmp_path, monkeypatch):
    db_path = tmp_path / "nested" / "main.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "sync_service.get_app_setting",
        lambda key, default=None: (
            "backups_auto" if key == "backup_root_path" else default
        ),
    )

    assert resolve_backup_root(str(db_path)) == str(db_path.parent / "backups_auto")


def test_apply_change_log_to_db_updates_and_deletes_people(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO people (name, role, email, report_receiver, active) VALUES (?, ?, ?, ?, ?)",
        ("Doe John", "Engineer", "john@example.com", 0, 1),
    )
    person_id = cur.lastrowid
    conn.commit()

    update_path = tmp_path / "people_update.jsonl"
    update_payload = {
        "operation": "update",
        "table": "people",
        "data": {
            "id": person_id,
            "email": "john.doe@example.com",
            "report_receiver": 1,
            "active": 0,
        },
    }
    update_path.write_text(
        json.dumps(update_payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    accepted, already_applied, conflicts = _apply_change_log_to_db(
        conn, str(update_path), {}, update_path.name
    )

    assert (accepted, already_applied, conflicts) == (1, 0, 0)
    updated = cur.execute(
        "SELECT email, report_receiver, active FROM people WHERE id=?", (person_id,)
    ).fetchone()
    assert updated == ("john.doe@example.com", 1, 0)

    delete_path = tmp_path / "people_delete.jsonl"
    delete_payload = {
        "operation": "delete",
        "table": "people",
        "data": {"id": person_id},
    }
    delete_path.write_text(
        json.dumps(delete_payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    accepted, already_applied, conflicts = _apply_change_log_to_db(
        conn, str(delete_path), {}, delete_path.name
    )

    assert (accepted, already_applied, conflicts) == (1, 0, 0)
    assert (
        cur.execute("SELECT 1 FROM people WHERE id=?", (person_id,)).fetchone() is None
    )
    conn.close()


def test_apply_change_log_to_db_updates_isolation_request_elements(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    cur.execute("INSERT INTO substations (name, location) VALUES (?, ?)", ("S1", "L1"))
    sub_id = cur.lastrowid
    cur.execute(
        "INSERT INTO elements (substation_id, element_type, name, breaker_category) VALUES (?, ?, ?, ?)",
        (sub_id, "Διακόπτης ΜΤ", "E1", "SF6"),
    )
    elem1_id = cur.lastrowid
    cur.execute(
        "INSERT INTO elements (substation_id, element_type, name, breaker_category) VALUES (?, ?, ?, ?)",
        (sub_id, "Διακόπτης ΜΤ", "E2", "SF6"),
    )
    elem2_id = cur.lastrowid
    cur.execute(
        "INSERT INTO isolation_requests (substation_id, start_datetime, end_datetime, status, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            sub_id,
            "2026-03-01 08:00:00",
            "2026-03-01 12:00:00",
            "Requested",
            "initial",
            "2026-03-01 07:00:00",
            "2026-03-01 07:00:00",
        ),
    )
    request_id = cur.lastrowid
    cur.execute(
        "INSERT INTO isolation_request_elements (request_id, element_id) VALUES (?, ?)",
        (request_id, elem1_id),
    )
    conn.commit()

    update_path = tmp_path / "isolation_update.jsonl"
    update_payload = {
        "operation": "update",
        "table": "isolation_requests",
        "data": {
            "id": request_id,
            "status": "Approved",
            "notes": "updated",
            "elements": [{"element_id": elem2_id}],
        },
    }
    update_path.write_text(
        json.dumps(update_payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    accepted, already_applied, conflicts = _apply_change_log_to_db(
        conn, str(update_path), {}, update_path.name
    )

    assert (accepted, already_applied, conflicts) == (1, 0, 0)
    row = cur.execute(
        "SELECT status, notes FROM isolation_requests WHERE id=?", (request_id,)
    ).fetchone()
    assert row == ("Approved", "updated")
    linked = cur.execute(
        "SELECT element_id FROM isolation_request_elements WHERE request_id=? ORDER BY element_id",
        (request_id,),
    ).fetchall()
    assert linked == [(elem2_id,)]
    conn.close()


def test_apply_change_log_to_db_ignores_derived_element_maintenance_date(tmp_path):
    db_path = tmp_path / "main.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    cur.execute("INSERT INTO substations (name, location) VALUES (?, ?)", ("S1", "L1"))
    sub_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO elements (
            id,
            substation_id,
            element_type,
            name,
            breaker_category,
            maintenance_date
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1594, sub_id, "Διακόπτης ΜΤ", "E1", "SF6", "2025-12-05"),
    )
    conn.commit()

    change_path = tmp_path / "element_insert.jsonl"
    change_payload = {
        "operation": "insert",
        "table": "elements",
        "data": {
            "id": 1594,
            "substation_id": sub_id,
            "element_type": "Διακόπτης ΜΤ",
            "name": "E1",
            "breaker_category": "SF6",
            "maintenance_date": "",
        },
    }
    change_path.write_text(
        json.dumps(change_payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    accepted, already_applied, conflicts = _apply_change_log_to_db(
        conn, str(change_path), {}, change_path.name
    )

    assert (accepted, already_applied, conflicts) == (0, 1, 0)
    row = cur.execute(
        "SELECT maintenance_date FROM elements WHERE id=?",
        (1594,),
    ).fetchone()
    assert row == ("2025-12-05",)
    conn.close()
