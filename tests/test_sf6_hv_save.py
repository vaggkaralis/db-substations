import DBrun
import reports
from database import init_db
from model_management import _normalize_sf6_measurement_payload_for_multi_valve
from openpyxl import Workbook, load_workbook
from reports import (
    _export_sf6_excel,
    _get_sf6_report_data,
    normalize_decimal_numeric_text,
)


def test_fetch_sf6_multiple_valves_by_element_reads_model_flag(tmp_path):
    db_path = tmp_path / "sf6_flag.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "Test Sub"))
    cur.execute(
        "INSERT INTO element_models (id, element_category, model_name, breaker_category, sf6_multiple_valves) VALUES (?, ?, ?, ?, ?)",
        (10, "Διακόπτης", "SF6 Multi", "SF6", 1),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, element_model_id, breaker_category) VALUES (?, ?, ?, ?, ?, ?)",
        (20, 1, "Διακόπτης ΥΤ", "Breaker 1", 10, "SF6"),
    )
    conn.commit()

    values = DBrun._fetch_sf6_multiple_valves_by_element(conn, [20])
    assert values == {20: True}
    assert DBrun._fetch_sf6_multiple_valves_by_element(conn, []) == {}
    conn.close()


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


def test_sf6_single_pressure_is_expanded_to_all_phases_for_background_storage():
    payload = {"sf6_pressure_gauge_value": "2.5"}
    normalized = _normalize_sf6_measurement_payload_for_multi_valve(payload, False)

    assert normalized["sf6_pressure_gauge_value"] == "2.5"
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }


def test_sf6_single_valve_uses_phase_a_when_model_is_switched_back_to_single():
    payload = {
        "sf6_pressure_gauge_values": {
            "phase_a": "2.5",
            "phase_b": "3.1",
            "phase_c": "4.7",
        }
    }
    normalized = _normalize_sf6_measurement_payload_for_multi_valve(payload, False)

    assert normalized["sf6_pressure_gauge_value"] == "2.5"
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }

    multi_valve = _normalize_sf6_measurement_payload_for_multi_valve(payload, True)
    assert multi_valve["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "3.1",
        "phase_c": "4.7",
    }


def test_normalize_prefill_element_payload_keeps_sf6_phase_pressure_values():
    app = object.__new__(DBrun.SubstationApp)
    payload = {
        "sf6_pressure_gauge_value": "2.5",
        "sf6_pressure_gauge_values": {
            "phase_a": "2.5",
            "phase_b": "2.5",
            "phase_c": "2.5",
        },
        "sf6_pressure_gauge_unit": "bar",
    }

    normalized = app._normalize_prefill_element_payload(payload)

    assert normalized["sf6_pressure_gauge_value"] == "2.5"
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }
    assert normalized["sf6_pressure_gauge_unit"] == "bar"


def test_normalize_prefill_element_payload_keeps_sf6_alarm_and_block_values():
    app = object.__new__(DBrun.SubstationApp)
    payload = {
        "extra_measurements": {
            "sf6_alarm_appearance_value": "3.2",
            "sf6_alarm_appearance_unit": "bar",
            "sf6_block_appearance_value": "4.8",
            "sf6_block_appearance_unit": "bar",
            "sf6_alarm_disappearance_value": "0.6",
            "sf6_alarm_disappearance_unit": "bar",
            "sf6_block_disappearance_value": "1.1",
            "sf6_block_disappearance_unit": "bar",
        }
    }

    normalized = app._normalize_prefill_element_payload(payload)

    assert normalized["sf6_alarm_appearance_value"] == "3.2"
    assert normalized["sf6_block_appearance_value"] == "4.8"
    assert normalized["sf6_alarm_disappearance_value"] == "0.6"
    assert normalized["sf6_block_disappearance_value"] == "1.1"


def test_sf6_pressure_widget_reference_falls_back_to_phase_a_for_multi_valve_ui():
    app = object.__new__(DBrun.SubstationApp)
    phase_a_widget = object()
    phase_b_widget = object()
    phase_c_widget = object()
    measurements = {
        "sf6_pressure_gauge_values": {
            "phase_a": phase_a_widget,
            "phase_b": phase_b_widget,
            "phase_c": phase_c_widget,
        }
    }

    assert app._get_sf6_pressure_widget_reference(measurements) is phase_a_widget


def test_sf6_legacy_single_value_is_expanded_when_prefill_payload_is_normalized():
    app = object.__new__(DBrun.SubstationApp)
    payload = {"sf6_pressure_gauge_value": "2.5"}

    normalized = app._normalize_prefill_element_payload(payload)

    assert normalized["sf6_pressure_gauge_value"] == "2.5"
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }


def test_sf6_storage_payload_is_canonicalized_before_save_roundtrip():
    app = object.__new__(DBrun.SubstationApp)
    payload = {
        "sf6_pressure_gauge_value": "2.5",
        "sf6_pressure_gauge_values": {
            "phase_a": "2.5",
            "phase_b": "",
            "phase_c": "",
        },
    }

    normalized = app._normalize_sf6_pressure_payload(payload, True)

    assert normalized["sf6_pressure_gauge_value"] == "2.5"
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }


def test_sf6_zero_values_are_not_dropped_when_normalizing_phase_data():
    app = object.__new__(DBrun.SubstationApp)
    payload = {
        "sf6_pressure_gauge_values": {
            "phase_a": "0",
            "phase_b": "",
            "phase_c": "",
        }
    }

    normalized = app._normalize_sf6_pressure_payload(payload, True)

    assert normalized["sf6_pressure_gauge_value"] == "0"
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "0",
        "phase_b": "0",
        "phase_c": "0",
    }


def test_sf6_serialized_save_payload_keeps_pressure_and_alarm_values():
    app = object.__new__(DBrun.SubstationApp)

    class TextWidget:
        def __init__(self, value=""):
            self.text = value

    measurements = {
        "sf6_pressure_gauge_values": {
            "phase_a": TextWidget("2.5"),
            "phase_b": TextWidget("2.6"),
            "phase_c": TextWidget("2.7"),
        },
        "sf6_pressure_gauge_unit": TextWidget("bar"),
        "sf6_alarm_appearance_value": TextWidget("3.2"),
        "sf6_alarm_appearance_unit": TextWidget("bar"),
        "sf6_block_appearance_value": TextWidget("4.8"),
        "sf6_block_appearance_unit": TextWidget("bar"),
        "sf6_alarm_disappearance_value": TextWidget("0.6"),
        "sf6_alarm_disappearance_unit": TextWidget("bar"),
        "sf6_block_disappearance_value": TextWidget("1.1"),
        "sf6_block_disappearance_unit": TextWidget("bar"),
    }

    payload = app._serialize_sf6_measurement_payload_fields(measurements)

    assert payload["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.6",
        "phase_c": "2.7",
    }
    assert payload["sf6_alarm_appearance_value"] == "3.2"
    assert payload["sf6_block_appearance_value"] == "4.8"
    assert payload["sf6_alarm_disappearance_value"] == "0.6"
    assert payload["sf6_block_disappearance_value"] == "1.1"


def test_measurement_toggle_auto_activates_when_sf6_value_is_entered():
    app = object.__new__(DBrun.SubstationApp)

    class Toggle:
        def __init__(self):
            self.active = False
            self.callbacks = {}

        def bind(self, **kwargs):
            self.callbacks.update(kwargs)

    class TextWidget:
        def __init__(self):
            self.text = ""
            self.callbacks = {}

        def bind(self, **kwargs):
            self.callbacks.update(kwargs)

    toggle = Toggle()
    widget = TextWidget()
    app._bind_measurement_toggle_autostart(
        {"sf6_pressure_gauge_values": {"phase_a": widget}}, toggle
    )

    widget.callbacks["text"](widget)

    assert toggle.active is True


def test_sf6_payload_fallback_serializes_widget_values_into_extra_measurements():
    app = object.__new__(DBrun.SubstationApp)

    class TextWidget:
        def __init__(self, value=""):
            self.text = value

    payload = {
        "sf6_pressure_gauge_values": {
            "phase_a": TextWidget("2.5"),
            "phase_b": TextWidget("2.6"),
            "phase_c": TextWidget("2.7"),
        },
        "sf6_alarm_appearance_value": TextWidget("3.2"),
        "sf6_block_appearance_value": TextWidget("4.8"),
        "post_sf6_quality": {"sf6_pct": (TextWidget("99.1"),)},
    }

    fallback = app._serialize_meaningful_payload_fields(
        payload,
        (
            "sf6_pressure_gauge_value",
            "sf6_pressure_gauge_values",
            "sf6_pressure_gauge_value_phase_a",
            "sf6_pressure_gauge_value_phase_b",
            "sf6_pressure_gauge_value_phase_c",
            "sf6_alarm_appearance_value",
            "sf6_block_appearance_value",
            "post_sf6_quality",
        ),
    )

    assert fallback["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.6",
        "phase_c": "2.7",
    }
    assert fallback["sf6_alarm_appearance_value"] == "3.2"
    assert fallback["sf6_block_appearance_value"] == "4.8"
    assert fallback["post_sf6_quality"]["sf6_pct"][0] == "99.1"


def test_sf6_alarm_and_pressure_fields_are_restored_on_prefill():
    app = object.__new__(DBrun.SubstationApp)

    class TextWidget:
        def __init__(self):
            self.text = ""

    phase_a = TextWidget()
    phase_b = TextWidget()
    phase_c = TextWidget()
    alarm_value = TextWidget()
    alarm_unit = TextWidget()
    block_value = TextWidget()
    block_unit = TextWidget()
    sf6_quality_value = TextWidget()
    measurements = {
        "sf6_pressure_gauge_values": {
            "phase_a": phase_a,
            "phase_b": phase_b,
            "phase_c": phase_c,
        },
        "sf6_alarm_appearance_value": alarm_value,
        "sf6_alarm_appearance_unit": alarm_unit,
        "sf6_block_appearance_value": block_value,
        "sf6_block_appearance_unit": block_unit,
        "post_sf6_quality": {"sf6_pct": (sf6_quality_value,)},
    }
    data = {
        "sf6_pressure_gauge_values": {
            "phase_a": "2.5",
            "phase_b": "2.6",
            "phase_c": "2.7",
        },
        "sf6_alarm_appearance_value": "3.2",
        "sf6_alarm_appearance_unit": "bar",
        "sf6_block_appearance_value": "4.8",
        "sf6_block_appearance_unit": "bar",
        "post_sf6_quality": {"sf6_pct": "99.1"},
    }

    app._apply_sf6_measurement_payload_to_widgets(measurements, data)

    assert phase_a.text == "2.5"
    assert phase_b.text == "2.6"
    assert phase_c.text == "2.7"
    assert alarm_value.text == "3.2"
    assert block_value.text == "4.8"
    assert sf6_quality_value.text == "99.1"


def test_sf6_model_flag_wins_even_when_existing_payload_is_legacy_single_value():
    app = object.__new__(DBrun.SubstationApp)
    payload = {"sf6_pressure_gauge_value": "2.5"}

    assert app._has_multi_valve_sf6_layout(payload, True) is True
    assert app._has_multi_valve_sf6_layout(payload, False) is False
    normalized = app._normalize_sf6_pressure_payload(payload, True)
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }


def test_sf6_single_model_flag_keeps_single_layout_even_when_phase_values_match():
    app = object.__new__(DBrun.SubstationApp)
    payload = {
        "sf6_pressure_gauge_values": {
            "phase_a": "2.5",
            "phase_b": "2.5",
            "phase_c": "2.5",
        }
    }

    assert app._has_multi_valve_sf6_layout(payload, False) is False
    assert app._has_multi_valve_sf6_layout(payload, True) is True


def test_meaningful_measurement_value_ignores_empty_widget_text():
    app = object.__new__(DBrun.SubstationApp)

    class EmptyTextWidget:
        def __init__(self):
            self.text = ""

    class ActiveWidget:
        def __init__(self):
            self.active = False

    assert app._has_meaningful_measurement_value(EmptyTextWidget()) is False
    assert app._has_meaningful_measurement_value(ActiveWidget()) is False


def test_sf6_nested_extra_measurements_are_detected_as_multi_valve_layout():
    app = object.__new__(DBrun.SubstationApp)
    payload = {
        "extra_measurements": {
            "sf6_pressure_gauge_values": {
                "phase_a": "2.5",
                "phase_b": "2.6",
                "phase_c": "2.7",
            }
        }
    }

    assert app._has_multi_valve_sf6_layout(payload, None) is True
    assert app._has_multi_valve_sf6_layout(payload, False) is False


def test_sf6_nested_extra_measurements_are_normalized_before_save_roundtrip():
    app = object.__new__(DBrun.SubstationApp)
    payload = {
        "extra_measurements": {
            "sf6_pressure_gauge_value": "2.5",
            "sf6_pressure_gauge_values": {
                "phase_a": "2.5",
                "phase_b": "",
                "phase_c": "",
            },
        }
    }

    normalized = app._normalize_sf6_pressure_payload(payload, True)
    assert normalized["sf6_pressure_gauge_value"] == "2.5"
    assert normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }

    model_normalized = _normalize_sf6_measurement_payload_for_multi_valve(payload, True)
    assert model_normalized["sf6_pressure_gauge_values"] == {
        "phase_a": "2.5",
        "phase_b": "2.5",
        "phase_c": "2.5",
    }


def test_sf6_measurements_are_saved_when_values_exist_even_if_toggle_is_off():
    app = object.__new__(DBrun.SubstationApp)
    phase_widgets = {
        "phase_a": type("Field", (), {"text": "2.5"})(),
        "phase_b": type("Field", (), {"text": "2.5"})(),
        "phase_c": type("Field", (), {"text": "2.5"})(),
    }
    measurements = {
        "sf6_pressure_gauge_values": phase_widgets,
        "sf6_pressure_gauge_unit": type("Unit", (), {"text": "bar"})(),
    }

    assert app._should_store_widget_measurements(measurements, False) is True
    assert (
        app._should_store_widget_measurements(
            {"other": type("Field", (), {"text": ""})()}, False
        )
        is False
    )


def test_sf6_alarm_and_block_values_are_preserved_in_save_payload():
    app = object.__new__(DBrun.SubstationApp)
    existing = {
        "sf6_alarm_appearance_value": "1.0",
        "sf6_block_appearance_value": "2.0",
        "sf6_alarm_disappearance_value": "0.5",
        "sf6_block_disappearance_value": "0.7",
    }
    current = {
        "sf6_pressure_gauge_value": "2.5",
        "sf6_alarm_appearance_value": "3.2",
        "sf6_block_appearance_value": "4.8",
        "sf6_alarm_disappearance_value": "0.6",
        "sf6_block_disappearance_value": "1.1",
        "measurements_enabled": True,
    }

    preserved = app._preserve_existing_measurement_payload(
        existing,
        current,
        measurements_enabled=True,
    )

    assert preserved["sf6_pressure_gauge_value"] == "2.5"
    assert preserved["sf6_alarm_appearance_value"] == "3.2"
    assert preserved["sf6_block_appearance_value"] == "4.8"
    assert preserved["sf6_alarm_disappearance_value"] == "0.6"
    assert preserved["sf6_block_disappearance_value"] == "1.1"


def test_sf6_boolish_flag_values_are_normalized_in_model_lookup():
    assert DBrun._coerce_bool_flag("0") is False
    assert DBrun._coerce_bool_flag("1") is True
    assert DBrun._coerce_bool_flag("false") is False
    assert DBrun._coerce_bool_flag("true") is True
    assert DBrun._get_sf6_multiple_valves_flag({862: True}, "862") is True
    assert DBrun._get_sf6_multiple_valves_flag({"862": True}, 862) is True


def test_sf6_db_flag_wins_over_stale_cached_model_lookup():
    # The cached map can be stale while the database reflects the current model.
    # In that case the DB value must win so the maintenance form stays aligned.
    conn = init_db(":memory:")
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "Test Sub"))
    cur.execute(
        "INSERT INTO element_models (id, element_category, model_name, breaker_category, sf6_multiple_valves) VALUES (?, ?, ?, ?, ?)",
        (24, "Διακόπτης", "SF6 Single", "SF6", 1),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, element_model_id, breaker_category) VALUES (?, ?, ?, ?, ?, ?)",
        (862, 1, "Διακόπτης ΥΤ", "Breaker 862", 24, "SF6"),
    )
    conn.commit()

    stale_map = {862: False}
    assert DBrun._resolve_sf6_multiple_valves_flag(conn, stale_map, 862) is True
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


def test_sf6_report_data_accumulates_leakage_per_element(tmp_path):
    db_path = tmp_path / "test_sf6_report_running_total.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "ΥΣ Α"))
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category, operating_status) VALUES (?, ?, ?, ?, ?, ?)",
        (10, 1, "Διακόπτης ΥΤ", "Q1", "SF6", "Ενεργή"),
    )
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (100, 1, "Leak 1", "2026-01-05"),
    )
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (101, 1, "Leak 2", "2026-02-10"),
    )
    cur.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, sf6_leakage_kg, sf6_leak_methodology) VALUES (?, ?, ?, ?)",
        (100, 10, 1.0, "Πλήρωση"),
    )
    cur.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, sf6_leakage_kg, sf6_leak_methodology) VALUES (?, ?, ?, ?)",
        (101, 10, 1.0, "Αντικατάσταση"),
    )
    conn.commit()

    class DummyApp:
        def __init__(self, connection):
            self.conn = connection

        def _format_maintenance_date(self, value):
            return value

    data = _get_sf6_report_data(DummyApp(conn), "2026")

    assert [row["element_total_leakage"] for row in data["rows"]] == [1.0, 2.0]
    assert data["leakage_bands"]["max"] == 2.0
    assert reports._classify_sf6_leakage(1.0, data["leakage_bands"]) == "green"
    assert reports._classify_sf6_leakage(2.0, data["leakage_bands"]) == "red"

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


def test_sf6_excel_export_uses_template_and_keeps_blank_leakage_rows(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "test_sf6_export.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    template_path = tmp_path / "ΚΣΜΘ ΥΣ SF6 2026.xlsx"
    template_substation_sheet = "ΥΣ ΔΟΚΙΜΗ"
    wb_template = Workbook()
    ws_summary = wb_template.active
    ws_summary.title = "Σύνοψη"
    ws_substation = wb_template.create_sheet(template_substation_sheet)
    for ws in (ws_summary, ws_substation):
        ws.cell(
            row=1, column=1, value="ΠΙΝΑΚΑΣ 4: ΠΗΓΗ ΕΚΠΟΜΠΩΝ ΑΠΌ ΕΞΟΠΛΙΣΜΟ ΧΡΗΣΗΣ SF6"
        )
        ws.cell(row=2, column=1, value="Α/Α")
        ws.cell(row=3, column=1, value=1)
        ws.cell(row=8, column=1, value="Σχόλια")
    wb_template.save(template_path)
    template_sheetnames = load_workbook(template_path, read_only=True).sheetnames
    monkeypatch.setattr(
        reports,
        "_resolve_sf6_template_path",
        lambda _year: str(template_path),
    )

    cur.execute(
        "INSERT INTO substations (id, name) VALUES (?, ?)",
        (1, template_substation_sheet),
    )
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

    output_path = _export_sf6_excel(DummyApp(conn), "2026")
    wb = load_workbook(output_path)

    assert wb.sheetnames == template_sheetnames

    ws = wb[template_substation_sheet]
    data_row = None
    for row_idx in range(3, 10):
        if ws.cell(row=row_idx, column=1).value == 1:
            data_row = row_idx
            break

    assert data_row == 3
    assert ws.cell(row=data_row, column=5).value == "Πλήρωση"
    assert ws.cell(row=data_row, column=7).value in (None, "")

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
