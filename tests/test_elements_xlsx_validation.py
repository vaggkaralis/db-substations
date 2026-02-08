import importers
import sqlite3


class FakePD:
    def __init__(self, rows, columns):
        self._rows = rows
        self.columns = columns

    def read_excel(self, path, sheet_name=None):
        return FakeDF(self._rows, self.columns)

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


def test_elements_xlsx_version_mismatch(monkeypatch):
    cols = [
        "Substation Name",
        "Element Type",
        "Name",
        "Serial Number",
        "Gate",
        "Operating Status",
    ]
    rows = [{cols[0]: "Version: v0.9"}]
    fake_pd = FakePD(rows, cols)
    monkeypatch.setitem(__import__("sys").modules, "pandas", fake_pd)
    importers.pd = fake_pd

    conn = sqlite3.connect(":memory:")

    errors = {}

    def on_success(msg):
        errors["ok"] = msg

    def on_error(msg):
        errors["err"] = msg

    importers.import_elements_from_excel(conn, "dummy.xlsx", on_success, on_error)

    assert "err" in errors
