import DBrun
from database import init_db

from reports import _get_sf6_report_data, normalize_decimal_numeric_text


def test_hv_sf6_leakage_persistence(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    # create minimal substation and element (HV breaker)
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "Test Sub"))
    conn.commit()

    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category) VALUES (?, ?, ?, ?, ?)",
        (766, 1, "Διακόπτης ΥΤ", "Ρ-200", "SF6"),
    )
    conn.commit()

    # Insert maintenance record
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (2912, 1, "Test Maint", "2026-01-05"),
    )
    conn.commit()

    # Insert maintenance_elements with SF6 leakage and methodology
    cur.execute(
        (
            "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments, sf6_leakage_kg, sf6_leak_methodology)"
            " VALUES (?, ?, ?, ?, ?)"
        ),
        (2912, 766, "Imported SF6", 0.5, "Πλήρωση"),
    )
    conn.commit()

    # Read back and assert
    cur.execute(
        "SELECT sf6_leakage_kg, sf6_leak_methodology FROM maintenance_elements WHERE maintenance_id=? AND element_id=?",
        (2912, 766),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 0.5
    assert row[1] == "Πλήρωση"

    conn.close()


def test_normalize_decimal_numeric_text_accepts_comma_and_dot():
    assert normalize_decimal_numeric_text("1,15") == "1.15"
    assert normalize_decimal_numeric_text("1.15") == "1.15"
    assert normalize_decimal_numeric_text("2,50", decimal_separator=",") == "2,50"


def test_normalize_decimal_numeric_text_handles_mixed_separators_and_spaces():
    assert normalize_decimal_numeric_text("1.234,56") == "1234.56"
    assert normalize_decimal_numeric_text("1,234.56") == "1234.56"
    assert normalize_decimal_numeric_text(" 1 234,56 ") == "1234.56"
    assert normalize_decimal_numeric_text("-0,75") == "-0.75"


def test_sf6_report_data_groups_by_substation_and_keeps_ids(tmp_path):
    db_path = tmp_path / "test_sf6_report.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "ΥΣ Α"))
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (2, "ΥΣ Β"))
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category, operating_status) VALUES (?, ?, ?, ?, ?, ?)",
        (10, 1, "Διακόπτης ΥΤ", "Q1", "SF6", "Ενεργή"),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category, operating_status) VALUES (?, ?, ?, ?, ?, ?)",
        (20, 2, "Διακόπτης ΜΤ", "Q2", "SF6", "Ενεργή"),
    )
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (100, 1, "Leak 1", "2026-01-05"),
    )
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (200, 2, "Leak 2", "2026-03-10"),
    )
    cur.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, sf6_leakage_kg, sf6_leak_methodology) VALUES (?, ?, ?, ?)",
        (100, 10, 0.25, "Πλήρωση"),
    )
    cur.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, sf6_leakage_kg, sf6_leak_methodology) VALUES (?, ?, ?, ?)",
        (200, 20, 1.10, "Αντικατάσταση"),
    )
    conn.commit()

    class DummyApp:
        def __init__(self, connection):
            self.conn = connection

        def _format_maintenance_date(self, value):
            return value

    data = _get_sf6_report_data(DummyApp(conn), "2026")

    assert set(data["available_substations"]) == {"ΥΣ Α", "ΥΣ Β"}
    assert len(data["substation_rows"]["ΥΣ Α"]) == 1
    assert len(data["substation_rows"]["ΥΣ Β"]) == 1
    assert data["substation_rows"]["ΥΣ Α"][0]["maintenance_id"] == 100
    assert data["substation_rows"]["ΥΣ Β"][0]["element_id"] == 20
    assert data["leakage_bands"]["max"] == 1.10

    conn.close()


def test_sf6_report_excludes_methodology_only_rows(tmp_path):
    db_path = tmp_path / "test_sf6_methodology_only.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "ΥΣ Α"))
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category, operating_status) VALUES (?, ?, ?, ?, ?, ?)",
        (10, 1, "Διακόπτης ΜΤ", "Q1", "SF6", "Ενεργή"),
    )
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (100, 1, "SF6 Method", "2026-04-20"),
    )
    cur.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, sf6_leak_methodology) VALUES (?, ?, ?)",
        (100, 10, "Πλήρωση"),
    )
    conn.commit()

    class DummyApp:
        def __init__(self, connection):
            self.conn = connection

        def _format_maintenance_date(self, value):
            return value

    data = _get_sf6_report_data(DummyApp(conn), "2026")

    assert data["rows"] == []

    conn.close()


def test_normalize_sf6_leakage_fields_clears_methodology_without_value():
    app = DBrun.SubstationApp()

    leakage, methodology = app._normalize_sf6_leakage_fields(None, "Πλήρωση")

    assert leakage is None
    assert methodology is None


def test_normalize_sf6_leakage_fields_keeps_methodology_with_value():
    app = DBrun.SubstationApp()

    leakage, methodology = app._normalize_sf6_leakage_fields(0.5, " Πλήρωση ")

    assert leakage == 0.5
    assert methodology == "Πλήρωση"


def test_preserve_existing_measurement_payload_keeps_sf6_values_on_blank_resave():
    app = DBrun.SubstationApp()

    existing_data = {
        "sf6_leakage_kg": 0.9,
        "sf6_leak_methodology": "Πλήρωση",
        "sf6": {
            "sf6_n2_fa": None,
            "h2o_fa": None,
            "so2_fa": None,
            "sf6_n2_fb": None,
            "h2o_fb": None,
            "so2_fb": None,
            "sf6_n2_fc": None,
            "h2o_fc": None,
            "so2_fc": None,
        },
        "vidar": {},
        "extra_measurements": {},
    }
    current_payload = {
        "ins_closed_fa": None,
        "ins_closed_fa_unit": "GΩ",
        "ins_closed_fb": None,
        "ins_closed_fb_unit": "GΩ",
        "ins_closed_fc": None,
        "ins_closed_fc_unit": "GΩ",
        "ins_open_fa": None,
        "ins_open_fa_unit": "GΩ",
        "ins_open_fb": None,
        "ins_open_fb_unit": "GΩ",
        "ins_open_fc": None,
        "ins_open_fc_unit": "GΩ",
        "cont_fa": None,
        "cont_fb": None,
        "cont_fc": None,
        "ops_count": None,
        "sf6_leakage_kg": None,
        "sf6_leak_methodology": None,
        "sf6": {},
        "vidar": {},
        "extra_measurements": {},
    }

    merged = app._preserve_existing_measurement_payload(
        existing_data,
        current_payload,
        measurements_enabled=True,
    )

    assert merged["sf6_leakage_kg"] == 0.9
    assert merged["sf6_leak_methodology"] == "Πλήρωση"


def test_preserve_existing_measurement_payload_keeps_new_values_when_present():
    app = DBrun.SubstationApp()

    existing_data = {
        "sf6_leakage_kg": 0.9,
        "sf6_leak_methodology": "Πλήρωση",
    }
    current_payload = {
        "ins_closed_fa": None,
        "ins_closed_fa_unit": "GΩ",
        "ins_closed_fb": None,
        "ins_closed_fb_unit": "GΩ",
        "ins_closed_fc": None,
        "ins_closed_fc_unit": "GΩ",
        "ins_open_fa": None,
        "ins_open_fa_unit": "GΩ",
        "ins_open_fb": None,
        "ins_open_fb_unit": "GΩ",
        "ins_open_fc": None,
        "ins_open_fc_unit": "GΩ",
        "cont_fa": None,
        "cont_fb": None,
        "cont_fc": None,
        "ops_count": None,
        "sf6_leakage_kg": 0.4,
        "sf6_leak_methodology": "Αντικατάσταση",
        "sf6": {},
        "vidar": {},
        "extra_measurements": {},
    }

    merged = app._preserve_existing_measurement_payload(
        existing_data,
        current_payload,
        measurements_enabled=True,
    )

    assert merged["sf6_leakage_kg"] == 0.4
    assert merged["sf6_leak_methodology"] == "Αντικατάσταση"
