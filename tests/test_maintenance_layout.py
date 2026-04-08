import android_app


def _collect_texts(widget):
    texts = []
    if hasattr(widget, "text"):
        texts.append(widget.text)
    for child in getattr(widget, "children", []):
        texts.extend(_collect_texts(child))
    return texts


def test_maintenance_comments_in_fixed_container(monkeypatch):
    # Capture the popup instance created by show_maintenance_menu
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            # no-op
            pass

        def dismiss(self):
            # no-op
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)

    app = android_app.SubstationAndroidApp()
    # call with a fake substation dict
    app.show_maintenance_menu(1, {"name": "S1"})

    popup = captured.get("instance")
    assert popup is not None
    # The popup content should be a layout; ensure it has a child TextInput
    # with the overall comments hint.
    found = False
    try:
        for child in getattr(popup.content, "children", []):
            # children may include the scroll and the comments container
            # inspect grandchildren for TextInput with hint_text
            for grand in getattr(child, "children", []):
                if getattr(grand, "hint_text", None) == (
                    "Γενικά σχόλια για την συντήρηση..."
                ):
                    found = True
    except Exception:
        found = False

    assert found, "Overall comments TextInput not found in fixed container"


def test_maintenance_menu_renders_gate_headers(monkeypatch):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)
    monkeypatch.setattr(
        android_app,
        "Clock",
        type(
            "DummyClock",
            (),
            {"schedule_once": staticmethod(lambda callback, _dt=0: callback(0))},
        ),
    )

    app = android_app.SubstationAndroidApp()
    app.data_mode = "local"
    elements = [
        {
            "id": 1,
            "name": "Breaker A",
            "element_type": "Διακόπτης ΜΤ",
            "breaker_category": "SF6",
            "serial_number": "SN-1",
            "model_manufacturer": "ABB",
            "model_name": "Model X",
            "voltage_level": "20kV",
            "manufacture_year": "2020",
            "operating_status": "Ενεργή",
            "gate": "ΠΥΛΗ 2",
        },
        {
            "id": 2,
            "name": "Breaker B",
            "element_type": "Διακόπτης ΜΤ",
            "breaker_category": "SF6",
            "serial_number": "SN-2",
            "model_manufacturer": "ABB",
            "model_name": "Model Y",
            "voltage_level": "20kV",
            "manufacture_year": "2021",
            "operating_status": "Ενεργή",
            "gate": "ΠΥΛΗ 1",
        },
    ]
    app._local_fetch_elements = lambda _substation_id: elements

    app.show_maintenance_menu(1, {"name": "S1"})

    texts = _collect_texts(captured["instance"].content)
    grouped = app._group_elements_by_gate(elements)
    assert [name for name, _ in grouped] == ["ΠΥΛΗ 1", "ΠΥΛΗ 2"]
    assert any("ΠΥΛΗ 1" in text for text in texts)
