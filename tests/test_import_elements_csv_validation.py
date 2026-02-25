import sqlite3

import importers


class FakePD:
    def __init__(self, rows, columns):
        self._rows = rows
        self.columns = columns

    def read_csv(self, path):
        return FakeDF(self._rows, self.columns)

    def read_excel(self, path, sheet_name=None):
        return FakeDF(self._rows, self.columns)

    @staticmethod
    def notna(v):
        return v is not None and v != ""


class FakeDF(list):
    def __init__(self, rows, columns):
        super().__init__(rows)
        self.columns = columns

    def __len__(self):
        return list.__len__(self)

    @property
    def iloc(self):
        class Iloc:
            def __init__(self, parent):
                self.parent = parent

            def __getitem__(self, idx):
                return self.parent[idx]

        return Iloc(self)

    def iterrows(self):
        for i, r in enumerate(self):
            yield i, r


def test_elements_csv_template_version_mismatch(monkeypatch, tmp_path):
    # create a fake DataFrame where first row contains an older Version
    cols = [
        "Substation Name",
        "Element Type",
        "Name",
        "Serial Number",
        "Gate",
        "Operating Status",
    ]
    # first row is the version marker row
    rows = [{cols[0]: "Version: v1.0"}]
    fake_pd = FakePD(rows, cols)
    monkeypatch.setitem(__import__("sys").modules, "pandas", fake_pd)
    importers.pd = fake_pd

    conn = sqlite3.connect(":memory:")

    errors = {}

    def on_success(msg):
        errors["ok"] = msg

    def on_error(msg):
        errors["err"] = msg

    # call importer - should invoke on_error due to template version mismatch
    importers.import_elements_from_csv(conn, "dummy.csv", on_success, on_error)

    assert "err" in errors
