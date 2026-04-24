import DBrun
import dbsubstations.strings as packaged_strings
import strings
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput


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
