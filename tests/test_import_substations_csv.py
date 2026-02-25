import sqlite3

from importers import import_substations_from_csv


class FakePD:
    def __init__(self, rows, columns=None):
        self._rows = rows
        self.columns = columns or (list(rows[0].keys()) if rows else [])

    def read_csv(self, path):
        return FakeDF(self._rows, self.columns)

    @staticmethod
    def notna(v):
        return v is not None and v != ""

    @staticmethod
    def isna(v):
        return not (v is not None and v != "")


class FakeDF(list):
    def __init__(self, rows, columns):
        super().__init__(rows)
        self.columns = columns

    def iterrows(self):
        for i, r in enumerate(self):
            yield i, r


def make_conn():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE substations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, location TEXT, adoption_date TEXT)"
    )
    conn.commit()
    return conn


def test_import_substations_from_csv_roundtrip(monkeypatch, tmp_path):
    # prepare fake CSV file (content isn't parsed by our fake pd)
    csv_path = tmp_path / "subs.csv"
    csv_path.write_text("Name,Location,Adoption Date\nS1,L1,2026-02-08\n", encoding="utf-8")

    rows = [{"Name": "S1", "Location": "L1", "Adoption Date": "2026-02-08"}]
    fake_pd = FakePD(rows)
    monkeypatch.setitem(__import__("sys").modules, "pandas", fake_pd)
    # also patch importers.pd directly in case module cached
    import importers

    importers.pd = fake_pd

    conn = make_conn()

    messages = {}

    def on_success(msg):
        messages["ok"] = msg

    def on_error(msg):
        messages["err"] = msg

    import_substations_from_csv(conn, str(csv_path), on_success, on_error)

    cur = conn.cursor()
    cur.execute("SELECT name, location, adoption_date FROM substations WHERE name=?", ("S1",))
    r = cur.fetchone()
    assert r == ("S1", "L1", "2026-02-08")
    assert "ok" in messages
