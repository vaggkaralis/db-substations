from pathlib import Path

from database import init_db
from onedrive_hybrid_storage import ensure_maintenance_folders


def _seed_multi_element_maintenance_fixture(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO substations (id, name, location) VALUES (1, 'TEST SUB', 'TEST LOC')"
    )
    cur.execute(
        """
        INSERT INTO elements
        (id, substation_id, element_type, name, gate, breaker_category)
        VALUES
        (14, 1, 'Μετασχηματιστής Ισχύος', 'T1', 'ΠΥΛΗ 1', NULL),
        (17, 1, 'Διακόπτης ΜΤ', 'Q17', 'ΠΥΛΗ 2', 'SF6'),
        (19, 1, 'Διακόπτης ΜΤ', 'Q19', 'ΠΥΛΗ 3', 'SF6')
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
            100, 1, 'Older Maintenance', '2026-03-25 08:00:00',
            'Ετήσια', 'tester', 'Overall ok'
        )
        """
    )
    for element_id in (14, 17, 19):
        cur.execute(
            "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
            (100, element_id, f"Element {element_id} ok"),
        )
    conn.commit()


def test_imported_maintenance_attachments_copy_once_to_primary_instance_folder(
    tmp_path,
):
    db_path = tmp_path / "test.db"
    conn = init_db(str(db_path))
    _seed_multi_element_maintenance_fixture(conn)

    source_dir = tmp_path / "incoming"
    source_dir.mkdir()
    first_attachment = source_dir / "older-report.pdf"
    first_attachment.write_bytes(b"%PDF-1.4\n%fake\n")
    second_attachment = source_dir / "older-measurements.xlsx"
    second_attachment.write_bytes(b"fake-xlsx")

    result = ensure_maintenance_folders(
        conn,
        maintenance_id=100,
        substation_id=1,
        maintenance_name="Older Maintenance",
        maintenance_type="Ετήσια",
        date_time="2026-03-25 08:00:00",
        element_ids=[14, 17, 19],
        attachment_paths=[str(first_attachment), str(second_attachment)],
        db_path=str(db_path),
    )

    primary_instance_folder = Path(result["primary_media_folder"])
    assert primary_instance_folder.is_dir()
    assert (primary_instance_folder / first_attachment.name).is_file()
    assert (primary_instance_folder / second_attachment.name).is_file()
    assert result["copied_media_count"] == 2
    assert result["copied_reports_count"] == 0

    copied_matches = list(primary_instance_folder.rglob(first_attachment.name)) + list(
        primary_instance_folder.rglob(second_attachment.name)
    )
    copied_paths = {
        path.relative_to(primary_instance_folder).as_posix() for path in copied_matches
    }
    assert len(copied_paths) == 2
    assert all("Αναφ_" not in copied_path for copied_path in copied_paths)

    report_rows = conn.execute(
        "SELECT COUNT(*) FROM maintenance_report_paths WHERE maintenance_id=?",
        (100,),
    ).fetchone()[0]
    assert report_rows == 0
