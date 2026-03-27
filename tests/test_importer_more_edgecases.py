import sqlite3

import importers


class FakePD:
    def __init__(self, rows, columns):
        self._rows = rows
        self.columns = columns

    def read_csv(self, path):
        return FakeDF(self._rows, self.columns)

    @staticmethod
    def notna(v):
        return v is not None and v != ""

    @staticmethod
    def isna(v):
        return not FakePD.notna(v)


class FakeDF(list):
    def __init__(self, rows, columns):
        super().__init__(rows)
        self.columns = columns

    def iterrows(self):
        for i, r in enumerate(self):
            yield i, r

    def __len__(self):
        return list.__len__(self)

    @property
    def iloc(self):
        class Iloc:
            def __init__(self, parent):
                self.parent = parent

            def __getitem__(self, idx):
                row = self.parent[idx]

                class RowLike:
                    def __init__(self, values):
                        self.values = values

                return RowLike(list(row.values()))

        return Iloc(self)


def test_import_elements_csv_missing_required_columns(monkeypatch):
    # create a fake DF missing required columns
    cols = ["Substation Name", "Name"]  # missing many required cols
    rows = [{"Substation Name": "S1", "Name": "E1"}]
    fake_pd = FakePD(rows, cols)
    monkeypatch.setitem(__import__("sys").modules, "pandas", fake_pd)
    importers.pd = fake_pd

    conn = sqlite3.connect(":memory:")

    result = {}

    def on_success(msg):
        result["ok"] = msg

    def on_error(msg):
        result["err"] = msg

    importers.import_elements_from_csv(conn, "dummy.csv", on_success, on_error)

    assert "err" in result


def test_import_elements_csv_model_mapping(monkeypatch):
    # Setup DB with a substation and element_models entry
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
    cur.execute(
        "CREATE TABLE element_models (id INTEGER PRIMARY KEY, element_category TEXT, model_name TEXT, manufacturer TEXT)"
    )
    cur.execute(
        "CREATE TABLE elements (id INTEGER PRIMARY KEY, substation_id INTEGER, element_type TEXT, name TEXT, serial_number TEXT, maintenance_date TEXT, voltage_level TEXT, manufacturer TEXT, gate TEXT, is_main_switch INTEGER, breaker_category TEXT, element_model_id INTEGER, operating_status TEXT)"
    )
    cur.execute("INSERT INTO substations (id, name) VALUES (?,?)", (1, "S1"))
    # insert model
    cur.execute(
        "INSERT INTO element_models (element_category, model_name, manufacturer) VALUES (?,?,?)",
        ("Διακόπτης ΜΤ", "M200", "Acme"),
    )
    conn.commit()

    # Prepare fake DF with version row then a valid element row matching model
    cols = [
        "Substation Name",
        "Element Type",
        "Name",
        "Serial Number",
        "Gate",
        "Operating Status",
        "Model Name",
        "Model Manufacturer",
    ]
    rows = [
        {
            "Substation Name": "S1",
            "Element Type": "Διακόπτης ΜΤ",
            "Name": "Breaker1",
            "Serial Number": "SN1",
            "Gate": "G1",
            "Operating Status": "Ενεργή",
            "Model Name": "M200",
            "Model Manufacturer": "Acme",
        },
    ]

    fake_pd = FakePD(rows, cols)
    monkeypatch.setitem(__import__("sys").modules, "pandas", fake_pd)
    importers.pd = fake_pd

    res = {}

    def on_success(msg):
        res["ok"] = msg

    def on_error(msg):
        res["err"] = msg

    importers.import_elements_from_csv(conn, "dummy.csv", on_success, on_error)

    # element should be inserted with element_model_id pointing to the model
    cur.execute("SELECT element_model_id FROM elements WHERE name=?", ("Breaker1",))
    row = cur.fetchone()
    assert row is not None and row[0] is not None
