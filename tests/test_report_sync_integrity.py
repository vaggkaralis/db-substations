from pathlib import Path

from database import init_db
from onedrive_hybrid_storage import (
    get_maintenance_overview_report_path,
    get_maintenance_report_path,
    regenerate_maintenance_reports,
    upsert_maintenance_report_path,
)
from report_sync import (
    ensure_maintenance_overview_reports,
    export_missing_reports,
    verify_maintenance_overview_report_synchronization,
    verify_report_synchronization,
)


def _seed_sample_data(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO substations (id, name, location) "
        "VALUES (1, 'TEST SUB', 'TEST LOC')"
    )
    cur.execute(
        """
        INSERT INTO elements
        (id, substation_id, element_type, name, gate, breaker_category)
        VALUES (10, 1, 'Διακόπτης ΥΤ', 'Q1', 'ΠΥΛΗ 1', 'SF6')
        """
    )
    cur.execute(
        """
        INSERT INTO maintenance
        (
            id, substation_id, name, date_time,
            maintenance_type, user_name, overall_comments
        )
        VALUES
        (
            100, 1, 'Annual Maintenance', '2026-03-25 08:00:00',
            'Ετήσια', 'tester', 'Overall ok'
        )
        """
    )
    cur.execute(
        "INSERT INTO maintenance_elements "
        "(maintenance_id, element_id, element_comments) VALUES "
        "(100, 10, 'Element ok')"
    )
    conn.commit()


def test_report_tracking_row_removed_when_pair_deleted(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    upsert_maintenance_report_path(
        conn,
        maintenance_id=100,
        element_id=10,
        report_path=str(tmp_path / "q1.pdf"),
    )
    conn.commit()
    assert get_maintenance_report_path(
        conn, maintenance_id=100, element_id=10, verify_exists=False
    )

    conn.execute(
        "DELETE FROM maintenance_elements WHERE maintenance_id=? AND element_id=?",
        (100, 10),
    )
    conn.commit()

    assert (
        get_maintenance_report_path(
            conn, maintenance_id=100, element_id=10, verify_exists=False
        )
        is None
    )


def test_upsert_rejects_stale_maintenance_element_pair(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    conn.execute(
        "DELETE FROM maintenance_elements WHERE maintenance_id=? AND element_id=?",
        (100, 10),
    )
    conn.commit()

    try:
        upsert_maintenance_report_path(
            conn,
            maintenance_id=100,
            element_id=10,
            report_path=str(tmp_path / "q1.pdf"),
        )
    except ValueError as exc:
        assert "stale maintenance-element pair" in str(exc)
    else:
        raise AssertionError("Expected ValueError for stale maintenance-element pair")


def test_ensure_maintenance_overview_reports_tracks_each_reports_root(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    gate1_reports = tmp_path / "gate1" / "Αναφορές"
    gate2_reports = tmp_path / "gate2" / "Αναφορές"
    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(gate1_reports),
            "now",
            100,
            "gate:2",
            str(tmp_path / "gate2"),
            str(tmp_path / "gate2" / "inst"),
            str(tmp_path / "gate2" / "media"),
            str(gate2_reports),
            "now",
        ),
    )
    conn.commit()

    def fake_generate(conn_, maintenance_id, output_path=None):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(
            b"%PDF-1.4\n%fake overview\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
            + b"0" * 1200
        )
        return output_path

    monkeypatch.setattr(
        "pdf_reports.generate_maintenance_overview_report", fake_generate
    )

    result = ensure_maintenance_overview_reports(
        conn, maintenance_id=100, db_path=str(tmp_path / "test.db")
    )

    assert result["errors"] == []
    assert result["generated"] == 2
    assert get_maintenance_overview_report_path(
        conn, maintenance_id=100, gate_key="gate:1", verify_exists=False
    )
    assert get_maintenance_overview_report_path(
        conn, maintenance_id=100, gate_key="gate:2", verify_exists=False
    )


def test_export_missing_reports_regenerates_missing_file_even_when_db_row_exists(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(tmp_path / "gate1" / "reports"),
            "now",
        ),
    )
    conn.execute(
        (
            "INSERT INTO maintenance_report_paths "
            "(maintenance_id, element_id, report_type, report_path, "
            "created_at, updated_at) VALUES (?, ?, 'pdf', ?, 'now', 'now')"
        ),
        (100, 10, str(tmp_path / "missing.pdf")),
    )
    conn.commit()

    calls = []

    def fake_safe_generate_and_store_report(*args, **kwargs):
        calls.append((kwargs["maintenance_id"], kwargs["element_id"]))
        return {"success": True, "action_taken": "created"}

    def fake_ensure_overview_reports(*args, **kwargs):
        return {"generated": 0, "updated": 0, "skipped": 0, "errors": []}

    monkeypatch.setattr(
        "report_sync.safe_generate_and_store_report",
        fake_safe_generate_and_store_report,
    )
    monkeypatch.setattr(
        "report_sync.ensure_maintenance_overview_reports", fake_ensure_overview_reports
    )

    result = export_missing_reports(conn, db_path=str(tmp_path / "test.db"))

    assert calls == [(100, 10)]
    assert result["generated"] == 1


def test_export_missing_reports_backfills_overview_when_element_pdf_already_exists(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    reports_root = tmp_path / "gate1" / "reports"
    tracked_pdf = reports_root / "existing.pdf"
    tracked_pdf.parent.mkdir(parents=True, exist_ok=True)
    tracked_pdf.write_bytes(
        b"%PDF-1.4\n%fake\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n" + b"0" * 1200
    )

    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(reports_root),
            "now",
        ),
    )
    conn.execute(
        (
            "INSERT INTO maintenance_report_paths "
            "(maintenance_id, element_id, report_type, report_path, "
            "created_at, updated_at) VALUES (?, ?, 'pdf', ?, 'now', 'now')"
        ),
        (100, 10, str(tracked_pdf)),
    )
    conn.commit()

    overview_calls = []

    def fake_safe_generate_and_store_report(*args, **kwargs):
        raise AssertionError(
            "Element report should not be regenerated when existing PDF is usable"
        )

    def fake_ensure_overview_reports(*args, **kwargs):
        overview_calls.append(kwargs["maintenance_id"])
        return {"generated": 1, "updated": 0, "skipped": 0, "errors": []}

    monkeypatch.setattr(
        "report_sync.safe_generate_and_store_report",
        fake_safe_generate_and_store_report,
    )
    monkeypatch.setattr(
        "report_sync.ensure_maintenance_overview_reports", fake_ensure_overview_reports
    )
    monkeypatch.setattr(
        "report_sync.repair_pdf_access",
        lambda path, **kwargs: True,
    )

    result = export_missing_reports(conn, db_path=str(tmp_path / "test.db"))

    assert result["generated"] == 0
    assert overview_calls == [100]


def test_ensure_maintenance_overview_reports_regenerates_invalid_existing_pdf(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    reports_root = tmp_path / "gate1" / "Αναφορές"
    reports_root.mkdir(parents=True, exist_ok=True)

    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(reports_root),
            "now",
        ),
    )
    conn.execute(
        (
            "INSERT INTO maintenance_overview_report_paths "
            "(maintenance_id, gate_key, report_type, report_path, "
            "created_at, updated_at) VALUES (?, ?, 'pdf_overview', ?, 'now', 'now')"
        ),
        (100, "gate:1", str(reports_root / "old_overview.pdf")),
    )
    conn.commit()

    def fake_generate(conn_, maintenance_id, output_path=None):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(
            b"%PDF-1.4\n%fixed overview\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
            + b"0" * 1200
        )
        return output_path

    monkeypatch.setattr(
        "pdf_reports.generate_maintenance_overview_report", fake_generate
    )
    monkeypatch.setattr(
        "report_sync.repair_pdf_access",
        lambda path, **kwargs: False,
    )

    result = ensure_maintenance_overview_reports(
        conn, maintenance_id=100, db_path=str(tmp_path / "test.db")
    )

    assert result["errors"] == []
    assert result["updated"] == 1


def test_verify_report_synchronization_uses_non_mutating_pdf_probe(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    reports_root = tmp_path / "gate1" / "reports"
    tracked_pdf = reports_root / "existing.pdf"
    tracked_pdf.parent.mkdir(parents=True, exist_ok=True)
    tracked_pdf.write_bytes(
        b"%PDF-1.4\n%fake\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n" + b"0" * 1200
    )

    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(reports_root),
            "now",
        ),
    )
    conn.execute(
        (
            "INSERT INTO maintenance_report_paths "
            "(maintenance_id, element_id, report_type, report_path, "
            "created_at, updated_at) VALUES (?, ?, 'pdf', ?, 'now', 'now')"
        ),
        (100, 10, str(tracked_pdf)),
    )
    conn.commit()

    calls = []

    def fake_repair(path, *, normalize_existing=True):
        calls.append((path, normalize_existing))
        return True

    monkeypatch.setattr("report_sync.repair_pdf_access", fake_repair)

    result = verify_report_synchronization(conn, db_path=str(tmp_path / "test.db"))

    assert result["missing_files"] == 0
    assert calls
    assert all(normalize_existing is False for _path, normalize_existing in calls)


def test_export_missing_reports_uses_non_mutating_pdf_probe_for_existing_files(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    reports_root = tmp_path / "gate1" / "reports"
    tracked_pdf = reports_root / "existing.pdf"
    tracked_pdf.parent.mkdir(parents=True, exist_ok=True)
    tracked_pdf.write_bytes(
        b"%PDF-1.4\n%fake\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n" + b"0" * 1200
    )

    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(reports_root),
            "now",
        ),
    )
    conn.execute(
        (
            "INSERT INTO maintenance_report_paths "
            "(maintenance_id, element_id, report_type, report_path, "
            "created_at, updated_at) VALUES (?, ?, 'pdf', ?, 'now', 'now')"
        ),
        (100, 10, str(tracked_pdf)),
    )
    conn.commit()

    calls = []

    def fake_repair(path, *, normalize_existing=True):
        calls.append((path, normalize_existing))
        return True

    monkeypatch.setattr("report_sync.repair_pdf_access", fake_repair)
    monkeypatch.setattr(
        "report_sync.ensure_maintenance_overview_reports",
        lambda *args, **kwargs: {
            "generated": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
        },
    )

    result = export_missing_reports(conn, db_path=str(tmp_path / "test.db"))

    assert result["generated"] == 0
    assert calls
    assert all(normalize_existing is False for _path, normalize_existing in calls)


def test_regenerate_maintenance_reports_uses_non_mutating_pdf_probe(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    reports_root = tmp_path / "gate1" / "reports"
    tracked_pdf = reports_root / "existing.pdf"
    tracked_pdf.parent.mkdir(parents=True, exist_ok=True)
    tracked_pdf.write_bytes(
        b"%PDF-1.4\n%fake\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n" + b"0" * 1200
    )

    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(reports_root),
            "now",
        ),
    )
    conn.commit()

    calls = []

    def fake_repair(path, *, normalize_existing=True):
        calls.append((path, normalize_existing))
        return True

    monkeypatch.setattr("pdf_reports.repair_pdf_access", fake_repair)
    monkeypatch.setattr(
        "report_sync.ensure_maintenance_overview_reports",
        lambda *args, **kwargs: {
            "generated": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
        },
    )

    result = regenerate_maintenance_reports(conn, db_path=str(tmp_path / "test.db"))

    assert result["generated"] == 0
    assert result["skipped"] == 1
    assert calls
    assert all(normalize_existing is False for _path, normalize_existing in calls)


def test_verify_overview_report_synchronization_uses_non_mutating_pdf_probe(
    tmp_path, monkeypatch
):
    conn = init_db(str(tmp_path / "test.db"))
    _seed_sample_data(conn)

    reports_root = tmp_path / "gate1" / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    overview_pdf = reports_root / "overview.pdf"
    overview_pdf.write_bytes(
        b"%PDF-1.4\n%fake overview\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
        + b"0" * 1200
    )

    conn.execute(
        """
        INSERT INTO maintenance_storage_paths
        (
            maintenance_id, gate_key, gate_folder, instance_folder,
            media_folder, reports_folder, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            100,
            "gate:1",
            str(tmp_path / "gate1"),
            str(tmp_path / "gate1" / "inst"),
            str(tmp_path / "gate1" / "media"),
            str(reports_root),
            "now",
        ),
    )
    conn.execute(
        (
            "INSERT INTO maintenance_overview_report_paths "
            "(maintenance_id, gate_key, report_type, report_path, "
            "created_at, updated_at) VALUES (?, ?, 'pdf_overview', ?, 'now', 'now')"
        ),
        (100, "gate:1", str(overview_pdf)),
    )
    conn.commit()

    calls = []

    def fake_repair(path, *, normalize_existing=True):
        calls.append((path, normalize_existing))
        return True

    monkeypatch.setattr("report_sync.repair_pdf_access", fake_repair)

    result = verify_maintenance_overview_report_synchronization(
        conn, db_path=str(tmp_path / "test.db")
    )

    assert result["missing_files"] == 0
    assert calls
    assert all(normalize_existing is False for _path, normalize_existing in calls)
