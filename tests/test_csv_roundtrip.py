import sqlite3
import csv
import tempfile
import os
import importers
from importers import import_substations_from_csv


class FakePD:
    def read_csv(self, path):
        rows = []
        with open(path, newline="", encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            for row in r:
                rows.append(row)
        return FakeDF(rows, r.fieldnames)

    @staticmethod
    def notna(v):
        return v is not None and v != ""


class FakeDF(list):
    def __init__(self, rows, columns):
        super().__init__(rows)
        self.columns = columns

    def iterrows(self):
        for i, r in enumerate(self):
            yield i, r


def make_db_with_substations(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS substations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, location TEXT, adoption_date TEXT)"
    )
    cur.execute(
        "INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)",
        ("S-A", "LocA", "2026-02-01"),
    )
    cur.execute(
        "INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)",
        ("S-B", "LocB", "2026-02-02"),
    )
    conn.commit()
    conn.close()


def test_csv_export_import_roundtrip(tmp_path):
    # create source DB and export its substations to CSV
    src_db = tmp_path / "src.db"
    make_db_with_substations(str(src_db))

    export_csv = tmp_path / "export.csv"
    # export by reading DB directly
    conn = sqlite3.connect(str(src_db))
    cur = conn.cursor()
    cur.execute("SELECT name, location, adoption_date FROM substations ORDER BY name")
    rows = cur.fetchall()
    conn.close()

    with open(export_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Name", "Location", "Adoption Date"])
        for r in rows:
            writer.writerow(r)

    # import into a new DB using import_substations_from_csv
    dest_conn = sqlite3.connect(":memory:")
    cur = dest_conn.cursor()
    cur.execute(
        "CREATE TABLE substations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, location TEXT, adoption_date TEXT)"
    )
    dest_conn.commit()

    messages = {}

    def on_success(msg):
        messages["ok"] = msg

    def on_error(msg):
        messages["err"] = msg

    # ensure importers sees a pandas-like object
    importers.pd = FakePD()
    import_substations_from_csv(dest_conn, str(export_csv), on_success, on_error)

    cur = dest_conn.cursor()
    cur.execute("SELECT name, location, adoption_date FROM substations ORDER BY name")
    imported = cur.fetchall()
    assert imported == rows
