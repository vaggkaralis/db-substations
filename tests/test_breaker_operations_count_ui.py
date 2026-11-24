import DBrun
import dbsubstations.strings as packaged_strings
import json
import sqlite3
import kivy.uix.popup as popup_module
import strings
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget


def test_clear_maintenance_date_filter_resets_both_spinners():
    date_filter = {"year": "2026", "month": "Νοε"}
    year_spinner = type("Spinner", (), {"text": "2026"})()
    month_spinner = type("Spinner", (), {"text": "Νοε"})()

    DBrun._clear_maintenance_date_filter(
        date_filter,
        year_spinner,
        month_spinner,
        "(Όλα έτη)",
        "(Όλοι οι μήνες)",
    )

    assert date_filter == {
        "year": "(Όλα έτη)",
        "month": "(Όλοι οι μήνες)",
    }
    assert year_spinner.text == "(Όλα έτη)"
    assert month_spinner.text == "(Όλοι οι μήνες)"


def _collect_texts(widget):
    texts = []
    text = getattr(widget, "text", None)
    if isinstance(text, str) and text:
        texts.append(text)
    for child in getattr(widget, "children", []) or []:
        texts.extend(_collect_texts(child))
    return texts


def test_breaker_operations_count_row_shows_last_value(monkeypatch):
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "TextInput", TextInput)

    app = object.__new__(DBrun.SubstationApp)

    row, ops_input = app._build_breaker_operations_count_row(321)

    assert getattr(ops_input, "hint_text", "") == "Αριθμός Χειρισμών"
    texts = _collect_texts(row)
    assert "Αριθμός Χειρισμών:" in texts
    assert "Τελευταία τιμή: 321" in texts

    summary = DBrun.SubstationApp._build_element_summary_text(
        object.__new__(DBrun.SubstationApp), {"operations_count": 321}
    )
    assert "Αριθμός Χειρισμών: 321" in summary


def test_selected_element_details_are_restored_during_bulk_edit_load():
    app = object.__new__(DBrun.SubstationApp)
    calls = []
    checkbox = type("Checkbox", (), {"active": True})()
    details = Widget()
    row = Widget()

    def ensure_details():
        if details.parent is None:
            row.add_widget(details)
        calls.append(True)

    widgets = {
        7: {
            "checkbox": checkbox,
            "ensure_details": ensure_details,
            "details_container": details,
        }
    }

    app._sync_selected_element_details_visibility(widgets)

    assert details.parent is row
    assert calls == [True]


def test_desktop_element_summary_includes_element_id():
    summary = DBrun.SubstationApp._build_element_summary_text(
        object.__new__(DBrun.SubstationApp),
        {
            "id": 77,
            "serial_number": "SN-1",
            "operations_count": 10,
        },
    )
    assert "ID: 77" in summary


def test_desktop_substation_summary_shows_base_and_10pct_reserve_oil_capacity(
    monkeypatch,
):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            name TEXT,
            gate TEXT,
            element_type TEXT,
            breaker_category TEXT,
            element_model_id INTEGER,
            substation_id INTEGER,
            parent_element_id INTEGER,
            operating_status TEXT
        );
        CREATE TABLE element_models (
            id INTEGER PRIMARY KEY,
            model_name TEXT,
            oil_capacity_l REAL,
            sf6_capacity_kg REAL,
            oil_weight_kg REAL
        );
        INSERT INTO element_models
            (id, model_name, oil_capacity_l, sf6_capacity_kg, oil_weight_kg)
        VALUES (1, 'Model Oil', 288, NULL, NULL);
        INSERT INTO elements
            (id, name, gate, element_type, breaker_category, element_model_id, substation_id, parent_element_id, operating_status)
        VALUES
            (1, 'Ρ-255', 'ΠΥΛΗ 1', 'Διακόπτης ΜΤ', 'Ελαίου', 1, 10, 0, 'Ενεργή');
        """
    )

    captured = {}

    class DummyPopup:
        def __init__(self, *args, **kwargs):
            self.content = None
            captured["popup"] = self

        def open(self):
            return None

        def dismiss(self):
            return None

    monkeypatch.setattr(popup_module, "Popup", DummyPopup)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = conn
    app.ELEM_BREAKER_YT = "Διακόπτης ΥΤ"
    app.ELEM_BREAKER_MT = "Διακόπτης ΜΤ"

    app.show_substation_element_summary(10, "ΓΡΕΒΕΝΑ", None)

    texts = _collect_texts(captured["popup"].content)
    joined = "\n".join(texts)
    assert "288 L / 2 βαρέλια" in joined
    assert "απόθεμα 10%: 316.8 L / 2 βαρέλια" in joined


def test_desktop_substation_summary_lists_hv_breakers_and_transformers_per_gate(
    monkeypatch,
):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            name TEXT,
            gate TEXT,
            element_type TEXT,
            breaker_category TEXT,
            element_model_id INTEGER,
            substation_id INTEGER,
            parent_element_id INTEGER,
            operating_status TEXT
        );
        CREATE TABLE element_models (
            id INTEGER PRIMARY KEY,
            model_name TEXT,
            oil_capacity_l REAL,
            sf6_capacity_kg REAL,
            oil_weight_kg REAL
        );
        INSERT INTO element_models
            (id, model_name, oil_capacity_l, sf6_capacity_kg, oil_weight_kg)
        VALUES
            (1, 'SF6 HV', NULL, 42, NULL),
            (2, 'TR 150/20', 12000, NULL, NULL);
        INSERT INTO elements
            (id, name, gate, element_type, breaker_category, element_model_id,
             substation_id, parent_element_id, operating_status)
        VALUES
            (1, 'Δ-101', 'ΠΥΛΗ 1', 'Διακόπτης ΥΤ', 'SF6', 1, 10, 0, 'Ενεργή'),
            (2, 'ΜΣ 1', 'ΠΥΛΗ 1', 'Μετασχηματιστής', 'Ελαίου', 2, 10, 0, 'Ενεργή');
        """
    )
    captured = {}

    class DummyPopup:
        def __init__(self, *args, **kwargs):
            self.content = None
            captured["popup"] = self

        def open(self):
            return None

        def dismiss(self):
            return None

    monkeypatch.setattr(popup_module, "Popup", DummyPopup)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = conn
    app.ELEM_BREAKER_YT = "Διακόπτης ΥΤ"
    app.ELEM_BREAKER_MT = "Διακόπτης ΜΤ"

    app.show_substation_element_summary(10, "ΥΠΟΣΤΑΘΜΟΣ", None)

    joined = "\n".join(_collect_texts(captured["popup"].content))
    assert "ΠΥΛΗ 1:" in joined
    assert "Διακόπτης ΥΤ Δ-101" in joined
    assert "Μοντέλο: SF6 HV | Κατηγορία: SF6 | SF6: 42 kg" in joined
    assert "Μετασχηματιστής ΜΣ 1" in joined
    assert "Μοντέλο: TR 150/20 | λάδι: 12000 L" in joined


def test_operations_count_strings_exist_in_both_modules():
    assert (
        strings.STRINGS_EL["MESSAGES"]["OPERATIONS_COUNT_LABEL"] == "Αριθμός Χειρισμών:"
    )
    assert strings.STRINGS_EN["MESSAGES"]["LAST_VALUE_LABEL"] == "Last value:"
    assert (
        packaged_strings.STRINGS_EL["MESSAGES"]["OPERATIONS_COUNT_HINT"]
        == "Αριθμός Χειρισμών"
    )
    assert (
        packaged_strings.STRINGS_EN["MESSAGES"]["OPERATIONS_COUNT_LABEL"]
        == "Operation Count:"
    )


def test_has_meaningful_measurement_value_ignores_empty_strings():
    app = object.__new__(DBrun.SubstationApp)

    assert app._has_meaningful_measurement_value(None) is False
    assert app._has_meaningful_measurement_value("") is False
    assert app._has_meaningful_measurement_value("   ") is False
    assert app._has_meaningful_measurement_value("Πλήρωση") is True
    assert app._has_meaningful_measurement_value(0) is True


def test_collect_measurement_widgets_keeps_always_visible_section(monkeypatch):
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "TextInput", TextInput)

    app = object.__new__(DBrun.SubstationApp)
    details_container = BoxLayout(orientation="vertical")
    fixed_widget = Widget()
    always_visible_widget = Label(text="Αριθμός Χειρισμών:")
    moved_widget = Label(text="Measurement")

    details_container.add_widget(fixed_widget)
    details_container.add_widget(always_visible_widget)
    details_container.add_widget(moved_widget)

    measurement_widgets = app._collect_measurement_widgets(
        details_container,
        {fixed_widget},
        [always_visible_widget],
    )

    assert measurement_widgets == [moved_widget]


def test_show_element_quick_view_displays_breaker_operations_count(monkeypatch):
    captured = {}

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return (
                "Ρ-240",
                "Διακόπτης ΜΤ",
                "3AH52/00000913",
                None,
                "Siemens",
                "2010",
                "Κυψέλη 1",
                "2024-02-02",
                26,
                175,
                None,
                "Κυψέλη 1",
                None,
            )

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakePopup:
        def __init__(self, *args, **kwargs):
            captured["popup"] = self
            self.content = None

        def open(self):
            captured["opened"] = True

        def dismiss(self):
            return None

    monkeypatch.setattr(popup_module, "Popup", FakePopup)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = FakeConnection()

    app._show_element_quick_view(441)

    assert captured.get("opened") is True
    texts = _collect_texts(captured["popup"].content)
    assert "Αριθμός Χειρισμών: 175" in texts


def test_show_element_quick_view_prefers_model_installation_space(monkeypatch):
    captured = {}

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return (
                "Ρ-240",
                "Διακόπτης ΜΤ",
                "3AH52/00000913",
                None,
                "Siemens",
                "2010",
                "",
                "2024-02-02",
                26,
                175,
                None,
                "Εσωτερικός",
                None,
            )

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakePopup:
        def __init__(self, *args, **kwargs):
            captured["popup"] = self
            self.content = None

        def open(self):
            captured["opened"] = True

        def dismiss(self):
            return None

    monkeypatch.setattr(popup_module, "Popup", FakePopup)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = FakeConnection()

    app._show_element_quick_view(441)

    assert captured.get("opened") is True
    texts = _collect_texts(captured["popup"].content)
    assert "Χώρος: Εσωτερικός" in texts


def test_prepare_measurement_details_payload_keeps_json_only_fields():
    app = object.__new__(DBrun.SubstationApp)

    payload = {
        "ops_count": 123,
        "sync_timing": {"open": ["10", "11", "12"]},
        "oil_condition": "Καλή",
        "empty_value": "   ",
    }

    prepared = app._prepare_measurement_details_payload(
        payload,
        exclude_keys=app._maintenance_detail_legacy_measurement_keys(),
    )

    assert "ops_count" not in prepared
    assert prepared == {
        "sync_timing": {"open": ["10", "11", "12"]},
        "oil_condition": "Καλή",
    }


def test_preserve_existing_measurement_payload_keeps_toggle_state():
    app = object.__new__(DBrun.SubstationApp)

    preserved = app._preserve_existing_measurement_payload(
        {},
        {
            "measurements_enabled": True,
            "extra_measurements": {"measurements_enabled": True, "ins_closed_fa": 5.2},
        },
        measurements_enabled=True,
    )

    assert preserved["measurements_enabled"] is True
    assert preserved["extra_measurements"]["measurements_enabled"] is True


def test_decode_saved_measurement_payload_handles_android_nested_measurements():
    app = object.__new__(DBrun.SubstationApp)

    extra_measurements, saved_toggle = app._decode_saved_measurement_payload(
        {
            "measurements_enabled": True,
            "measurements": {"ins_closed_fa": 6.7, "ops_count": 9},
        }
    )

    assert saved_toggle is True
    assert extra_measurements["measurements_enabled"] is True
    assert extra_measurements["ins_closed_fa"] == 6.7
    assert extra_measurements["ops_count"] == 9


def test_normalize_prefill_element_payload_restores_android_comments_and_measurements():
    app = object.__new__(DBrun.SubstationApp)

    normalized = app._normalize_prefill_element_payload(
        {
            "element_comments": "συντήρηση",
            "measurements_enabled": True,
            "measurements": {"ins_closed_fa": 6.7, "ops_count": 9},
            "operations_count": 11,
        }
    )

    assert normalized["element_comments"] == "συντήρηση"
    assert normalized["measurements_enabled"] is True
    assert normalized["extra_measurements"]["ins_closed_fa"] == 6.7
    assert normalized["ops_count"] == 9


def test_normalize_form_measurement_payload_maps_legacy_android_aliases():
    app = object.__new__(DBrun.SubstationApp)

    normalized = app._normalize_form_measurement_payload(
        {
            "operations_count": 11,
            "measurements": {"ins_closed_fa": 6.7, "sf6_leakage": 2.2},
        }
    )

    assert normalized["ops_count"] == 11
    assert normalized["extra_measurements"]["sf6_leakage_kg"] == 2.2
    assert normalized["ins_closed_fa"] == 6.7


def test_normalize_form_measurement_payload_maps_oil_quantity_aliases():
    app = object.__new__(DBrun.SubstationApp)

    normalized = app._normalize_form_measurement_payload({"oil_liters": 240})

    assert normalized["oil_quantity_l"] == 240


def test_format_measurement_details_payload_formats_nested_values():
    app = object.__new__(DBrun.SubstationApp)

    text = app._format_measurement_details_payload(
        {
            "sync_timing": {"open": ["10", "11", "12"]},
            "oil_changed": True,
        }
    )

    assert "Έλεγχος ταυτοχρονισμού:" in text
    assert "O:" in text
    assert "ΦΑΣΗ Α: 10" in text
    assert "Αλλαγή λαδιών: Ναι" in text


def test_collect_vidar_display_entries_prefers_structured_status_and_comment():
    app = object.__new__(DBrun.SubstationApp)

    entries = app._collect_vidar_display_entries(
        {
            "vidar_status": {
                "vidar_fa": "OK",
                "vidar_fb": "NOK",
            },
            "vidar_comment": {
                "vidar_fb": "Χρειάζεται επανέλεγχος",
            },
        },
        legacy_vidar={
            "vidar_fa": 1.0,
            "vidar_fb": 0.0,
            "vidar_fc": 1.0,
        },
    )

    assert entries == [
        ("ΦΑ-ΦΑ", "OK"),
        ("ΦΒ-ΦΒ", "NOK | Σχόλιο: Χρειάζεται επανέλεγχος"),
        ("ΦΓ-ΦΓ", "OK"),
    ]


def test_legacy_vidar_display_value_maps_binary_values():
    app = object.__new__(DBrun.SubstationApp)

    assert app._legacy_vidar_display_value(1) == "OK"
    assert app._legacy_vidar_display_value(0) == "NOK"
    assert app._legacy_vidar_display_value(2.5) == "2.5"


def test_receiving_breaker_contact_measurements_round_trip_through_serialization(
    monkeypatch,
):
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "TextInput", TextInput)

    app = object.__new__(DBrun.SubstationApp)
    details_container = BoxLayout(orientation="vertical")
    measurements = {
        "contact_bus_departure": app._add_three_phase_measurement_row(
            details_container,
            "Αντίσταση Διέλευσης Ζυγού-Αναχώρησης (uΩ):",
        ),
        "contact_departure_departure": app._add_three_phase_measurement_row(
            details_container,
            "Αντίσταση Διέλευσης Αναχώρησης-Αναχώρησης (uΩ):",
        ),
    }
    measurements["contact_bus_departure"][0].text = "12.5"
    measurements["contact_departure_departure"][2].text = "8.4"

    payload = app._serialize_measurements_for_storage(measurements)

    restored_container = BoxLayout(orientation="vertical")
    restored_measurements = {
        "contact_bus_departure": app._add_three_phase_measurement_row(
            restored_container,
            "Αντίσταση Διέλευσης Ζυγού-Αναχώρησης (uΩ):",
        ),
        "contact_departure_departure": app._add_three_phase_measurement_row(
            restored_container,
            "Αντίσταση Διέλευσης Αναχώρησης-Αναχώρησης (uΩ):",
        ),
    }
    app._apply_serialized_measurement_value(restored_measurements, payload)

    assert restored_measurements["contact_bus_departure"][0].text == "12.5"
    assert restored_measurements["contact_departure_departure"][2].text == "8.4"


def test_build_measurement_summary_formats_structured_vidar_and_receiving_contact_values():
    app = object.__new__(DBrun.SubstationApp)

    summary = app._build_maintenance_element_measurement_summary(
        elem_type=DBrun.SubstationApp.ELEM_BREAKER_MT,
        breaker_category="Κενού",
        cont_fa=10,
        cont_fb=11,
        cont_fc=12,
        extra_measurements_json=json.dumps(
            {
                "vidar_status": {
                    "vidar_fa": "OK",
                    "vidar_fb": "NOK",
                },
                "vidar_comment": {
                    "vidar_fb": "Απαιτείται παρατήρηση",
                },
                "contact_bus_departure": ["14", "15", "16"],
                "contact_departure_departure": ["17", "18", "19"],
            },
            ensure_ascii=False,
        ),
    )

    assert "Έλεγχος Κενού VIDAR" in summary
    assert "ΦΒ-ΦΒ:[/b] NOK | Σχόλιο: Απαιτείται παρατήρηση" in summary
    assert "Αντίσταση Διέλευσης Ζυγού-Αναχώρησης" in summary
    assert "ΦΑ-ΦΑ:[/b] 14 uOhm" in summary


def test_build_transformer_measurement_section_adds_labels_and_persistent_keys(
    monkeypatch,
):
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "TextInput", TextInput)
    monkeypatch.setattr(DBrun, "Spinner", Spinner)

    app = object.__new__(DBrun.SubstationApp)
    details_container = BoxLayout(orientation="vertical")
    measurements = {}

    app._build_transformer_measurement_section(details_container, measurements)

    texts = _collect_texts(details_container)
    assert "ΕΛΕΓΧΟΣ ΓΙΑ ΘΡΑΥΣΗ:" in texts
    assert "ΕΛΕΓΧΟΣ ΣΤΑΘΜΗΣ ΕΛΑΙΟΥ:" in texts
    assert "H1-1" in texts
    assert "satyf_counter" in measurements
    assert "insulators_checks" in measurements
    assert len(measurements["insulators_checks"]) == 4
    assert len(measurements["diverter_res"]) == 6


def test_transformer_measurement_groups_round_trip_through_serialization(monkeypatch):
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "TextInput", TextInput)
    monkeypatch.setattr(DBrun, "Spinner", Spinner)

    app = object.__new__(DBrun.SubstationApp)

    original_container = BoxLayout(orientation="vertical")
    original_measurements = {}
    app._build_transformer_measurement_section(
        original_container, original_measurements
    )
    original_measurements["insulators_checks"][0].text = "ΟΚ"
    original_measurements["oil_checks"][1].text = "Συμπληρώθηκε"
    original_measurements["diverter_res"][0].text = "7.6"

    payload = app._serialize_measurements_for_storage(original_measurements)

    restored_container = BoxLayout(orientation="vertical")
    restored_measurements = {}
    app._build_transformer_measurement_section(
        restored_container, restored_measurements
    )
    app._apply_serialized_measurement_value(restored_measurements, payload)

    assert restored_measurements["insulators_checks"][0].text == "ΟΚ"
    assert restored_measurements["oil_checks"][1].text == "Συμπληρώθηκε"
    assert restored_measurements["diverter_res"][0].text == "7.6"


def test_show_maintenance_element_details_hv_breaker_hides_insulation_sections(
    monkeypatch,
):
    captured = {}

    class FakeCursor:
        def __init__(self):
            self._last_query = ""

        def execute(self, query, _params=None):
            self._last_query = query
            return self

        def fetchone(self):
            if "SELECT m.name, m.date_time" in self._last_query:
                return (
                    "M1",
                    "2026-04-28 10:00:00",
                    "Γενικό σχόλιο",
                    "Περιοδική",
                    "tester",
                    "ΥΣ 1",
                    "Loc",
                    "Div",
                    DBrun.SubstationApp.ELEM_BREAKER_YT,
                    "Q1",
                    "SN1",
                    "ABB",
                    "Model1",
                    "SF6",
                    "150KV",
                    "Π1",
                    "H1",
                    "2020",
                    None,
                    None,
                    None,
                )
            if "SELECT me.element_comments" in self._last_query:
                return (
                    "Σχόλιο στοιχείου",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "10",
                    "11",
                    "12",
                    5,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    json.dumps({"oil_condition": "Καλή"}, ensure_ascii=False),
                    "SF6",
                )
            if "SELECT substation_id FROM maintenance" in self._last_query:
                return (1,)
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakePopup:
        def __init__(self, *args, **kwargs):
            captured["popup"] = self
            self.content = None

        def open(self):
            captured["opened"] = True

        def dismiss(self):
            return None

    monkeypatch.setattr(DBrun, "Popup", FakePopup)
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "GridLayout", GridLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "Button", Button)
    monkeypatch.setattr(DBrun, "ScrollView", ScrollView)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = FakeConnection()

    app.show_maintenance_element_details(1, 2, "Q1")

    assert captured.get("opened") is True
    texts = _collect_texts(captured["popup"].content)
    assert "Αντίσταση Μόνωσης - Διακόπτης Κλειστός (Γη)" not in texts
    assert "Αντίσταση Μόνωσης - Διακόπτης Ανοικτός (Φάση-Φάση)" not in texts
    assert "Καταχωρημένα δεδομένα φόρμας" not in texts
    assert "[b]Αντίσταση Διαβάσεως (uOhm)[/b]" in texts
    assert "Κατάσταση λαδιού: Καλή" in texts


def test_show_maintenance_element_details_mv_oil_breaker_shows_oil_quantity_field(
    monkeypatch,
):
    captured = {}

    class FakeCursor:
        def __init__(self):
            self._last_query = ""

        def execute(self, query, _params=None):
            self._last_query = query
            return self

        def fetchone(self):
            if "SELECT m.name, m.date_time" in self._last_query:
                return (
                    "M1",
                    "2026-04-28 10:00:00",
                    "Γενικό σχόλιο",
                    "Περιοδική",
                    "tester",
                    "ΥΣ 1",
                    "Loc",
                    "Div",
                    DBrun.SubstationApp.ELEM_BREAKER_MT,
                    "Q1",
                    "SN1",
                    "ABB",
                    "Model1",
                    "Ελαίου",
                    "20KV",
                    "Π1",
                    "H1",
                    "2020",
                    None,
                    None,
                    None,
                )
            if "SELECT me.element_comments" in self._last_query:
                return (
                    "Σχόλιο στοιχείου",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "10",
                    "11",
                    "12",
                    5,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    json.dumps(
                        {"oil_condition": "Καλή", "oil_quantity_l": 240},
                        ensure_ascii=False,
                    ),
                    "Ελαίου",
                )
            if "SELECT substation_id FROM maintenance" in self._last_query:
                return (1,)
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakePopup:
        def __init__(self, *args, **kwargs):
            captured["popup"] = self
            self.content = None

        def open(self):
            captured["opened"] = True

        def dismiss(self):
            return None

    monkeypatch.setattr(DBrun, "Popup", FakePopup)
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "GridLayout", GridLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "Button", Button)
    monkeypatch.setattr(DBrun, "ScrollView", ScrollView)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = FakeConnection()

    app.show_maintenance_element_details(1, 2, "Q1")

    assert captured.get("opened") is True
    texts = _collect_texts(captured["popup"].content)
    assert "[b]Ποσότητα λαδιού (L):[/b]" in texts
    assert "240" in texts


def test_show_maintenance_full_report_includes_element_form_data(monkeypatch):
    captured = {}

    class FakeCursor:
        def __init__(self):
            self._last_query = ""

        def execute(self, query, _params=None):
            self._last_query = query
            return self

        def fetchone(self):
            if "SELECT m.id, m.name, m.date_time" in self._last_query:
                return (
                    2973,
                    "M1",
                    "2026-11-11 12:49:00",
                    "",
                    "Επαναληπτική συντήρηση",
                    "",
                    38,
                    "ΣΕΡΡΕΣ",
                    "Loc",
                    "ΤΜΘ",
                    None,
                )
            return None

        def fetchall(self):
            if "FROM maintenance_elements me" in self._last_query:
                return [
                    (
                        1321,
                        DBrun.SubstationApp.ELEM_BREAKER_YT,
                        "Ρ-35",
                        "8383305",
                        "",
                        "SF6",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        116,
                        None,
                        "Πλήρωση",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        json.dumps(
                            {
                                "sync_timing": {
                                    "open": ["24.5", "23.5", "24.5"],
                                    "close": ["33.7", "31.7", "31.7"],
                                },
                                "resistance_raid": ["36", "36", "30"],
                            },
                            ensure_ascii=False,
                        ),
                    )
                ]
            return []

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakePopup:
        def __init__(self, *args, **kwargs):
            captured["popup"] = self
            self.content = None

        def open(self):
            captured["opened"] = True

        def dismiss(self):
            return None

    monkeypatch.setattr(DBrun, "Popup", FakePopup)
    monkeypatch.setattr(DBrun, "BoxLayout", BoxLayout)
    monkeypatch.setattr(DBrun, "GridLayout", GridLayout)
    monkeypatch.setattr(DBrun, "Label", Label)
    monkeypatch.setattr(DBrun, "Button", Button)
    monkeypatch.setattr(DBrun, "ScrollView", ScrollView)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = FakeConnection()
    app._get_ui_font_kwargs = lambda: {}
    app._get_maintenance_people = lambda _maintenance_id: (None, [])
    app.BREAKER_CATEGORIES_ALL = ["SF6", "Vacuum", "Κενού", "Ελαίου"]

    app.show_maintenance_full_report(2973)

    assert captured.get("opened") is True
    texts = _collect_texts(captured["popup"].content)
    joined_text = "\n".join(texts)
    assert "[b]Μετρήσεις Συντήρησης[/b]" in joined_text
    assert "[b]Αριθμός Χειρισμών:[/b] 116" in joined_text
    assert "[b]Καταχωρημένα Δεδομένα Φόρμας[/b]" in joined_text
    assert "[b]Έλεγχος ταυτοχρονισμού (ms)[/b]" in joined_text
    assert "[b]Μέτρηση Αντίστασης Διαβάσεως (uOhm)[/b]" in joined_text
