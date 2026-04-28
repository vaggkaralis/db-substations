import DBrun
import dbsubstations.strings as packaged_strings
import kivy.uix.popup as popup_module
import strings
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget


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
