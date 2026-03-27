import os
import sqlite3
import sys

# Ensure project root is on sys.path for direct script execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import inspect  # noqa: E402

import importers  # noqa: E402
from strings import STRINGS as S  # noqa: E402

ELEM_BREAKER_MT = S.get("MESSAGES", {}).get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")

print("--- import_elements_from_csv source ---")
print(inspect.getsource(importers.import_elements_from_csv))
print("--- end source ---")


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


rows = [
    {
        "Substation Name": "S1",
        "Element Type": ELEM_BREAKER_MT,
        "Name": "Breaker1",
        "Serial Number": "SN1",
        "Gate": "G1",
        "Operating Status": "Ενεργή",
        "Model Name": "M200",
        "Model Manufacturer": "Acme",
    }
]
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
fake_pd = FakePD(rows, cols)
importers.pd = fake_pd

conn = sqlite3.connect(":memory:")
cur = conn.cursor()
cur.execute("CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
cur.execute(
    """
    CREATE TABLE element_models (
        id INTEGER PRIMARY KEY,
        element_category TEXT,
        model_name TEXT,
        manufacturer TEXT
    )
    """
)
cur.execute(
    """
    CREATE TABLE elements (
        id INTEGER PRIMARY KEY,
        substation_id INTEGER,
        element_type TEXT,
        name TEXT,
        serial_number TEXT,
        maintenance_date TEXT,
        voltage_level TEXT,
        manufacturer TEXT,
        gate TEXT,
        is_main_switch INTEGER,
        breaker_category TEXT,
        element_model_id INTEGER,
        operating_status TEXT
    )
    """
)
cur.execute("INSERT INTO substations (id, name) VALUES (?,?)", (1, "S1"))
cur.execute(
    """
    INSERT INTO element_models (element_category, model_name, manufacturer)
    VALUES (?, ?, ?)
    """,
    (ELEM_BREAKER_MT, "M200", "Acme"),
)
conn.commit()


def on_success(msg):
    print("SUCCESS:", msg)


def on_error(msg):
    print("ERROR:", msg)


importers.import_elements_from_csv(conn, "dummy.csv", on_success, on_error)

print("ELEMENT MODELS:")
for row in cur.execute(
    """
    SELECT id, element_category, model_name, manufacturer
    FROM element_models
    """
):
    print(row)

print("ELEMENTS:")
for row in cur.execute(
    """
    SELECT
        id,
        substation_id,
        element_type,
        name,
        serial_number,
        element_model_id,
        operating_status
    FROM elements
    """
):
    print(row)
