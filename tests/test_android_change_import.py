import json
import os
import sqlite3
import tempfile

from database import init_db
from DBrun import apply_change_log_to_db
import imports


def test_android_change_import():
    # Create temp DB
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = init_db(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Insert a substation and an element so maintenance can reference it
        cur.execute(
            "INSERT INTO substations (name, location) VALUES (?, ?)", ("S1", "Loc1")
        )
        sub_id = cur.lastrowid
        cur.execute(
            (
                "INSERT INTO elements (substation_id, element_type, name, "
                "breaker_category) VALUES (?, ?, ?, ?)"
            ),
            (sub_id, "Διακόπτης ΜΤ", "Elem1", "SF6"),
        )
        elem_id = cur.lastrowid
        conn.commit()

        # Create a change log with a maintenance insert referencing elem_id
        fd2, changelog = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd2)
        try:
            maintenance_payload = {
                "substation_id": sub_id,
                "date_time": "2026-02-08 12:00:00",
                "overall_comments": "Test maintenance",
                "maintenance_type": "Επαναληπτική συντήρηση",
                "elements": [{"element_id": elem_id, "element_comments": "Checked"}],
            }
            with open(changelog, "w", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "operation": "insert",
                            "table": "maintenance",
                            "data": maintenance_payload,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            # Apply change log
            apply_change_log_to_db(conn, changelog)

            # Verify maintenance inserted
            cur.execute(
                (
                    "SELECT id, substation_id, date_time, overall_comments "
                    "FROM maintenance WHERE substation_id=?"
                ),
                (sub_id,),
            )
            rows = cur.fetchall()
            assert len(rows) == 1
            m = rows[0]
            assert m[2] == "2026-02-08 12:00:00"
            assert m[3] == "Test maintenance"

            # Verify maintenance_elements
            cur.execute(
                (
                    "SELECT maintenance_id, element_id, element_comments "
                    "FROM maintenance_elements WHERE maintenance_id=?"
                ),
                (m[0],),
            )
            elems = cur.fetchall()
            assert len(elems) == 1
            assert elems[0][1] == elem_id
            assert elems[0][2] == "Checked"

        finally:
            os.remove(changelog)
    finally:
        conn.close()
        os.remove(db_path)


def test_android_change_import_dialog_accepts_txt(monkeypatch):
    captured = {}

    class _App:
        def import_android_changes_from_file(self, file_path):
            captured["import_path"] = file_path

    def _fake_open_file_chooser_and_import(
        app,
        parent_popup,
        import_callback,
        title=None,
        filetypes=None,
        chooser_filters=None,
    ):
        captured["title"] = title
        captured["filetypes"] = filetypes
        captured["chooser_filters"] = chooser_filters

    monkeypatch.setattr(
        imports,
        "_open_file_chooser_and_import",
        _fake_open_file_chooser_and_import,
    )

    imports.show_import_android_changes_dialog(_App(), None)

    assert captured["filetypes"] == (
        ("Αρχεία change log Android", "*.json *.jsonl *.txt"),
    )
    assert captured["chooser_filters"] == ["*.json", "*.jsonl", "*.txt"]
