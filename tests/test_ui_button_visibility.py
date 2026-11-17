from android_app import SubstationAndroidApp


def test_root_buttons_visible_and_hidden(monkeypatch):
    app = SubstationAndroidApp()
    # Build UI to create root buttons
    app.build()
    assert hasattr(app, "refresh_btn")
    assert hasattr(app, "header_area")
    # Buttons should be enabled/visible
    assert app.refresh_btn.disabled is False
    assert app.refresh_btn.opacity == 1
    assert app.header_area.size_hint_y == 0.10
    assert app.header_area.opacity == 1

    # Prepare a dummy substation and call show_substation_details
    app.substations = [{"id": 99, "name": "T1", "location": ""}]
    # Call the view - should hide the root buttons
    app.show_substation_details(99)
    assert app.refresh_btn.disabled is True
    assert app.refresh_btn.opacity == 0
    assert app.header_area.size_hint_y == 0
    assert app.header_area.opacity == 0

    # Calling load_substations should restore the buttons
    app.load_substations(None)
    assert app.refresh_btn.disabled is False
    assert app.refresh_btn.opacity == 1
    assert app.header_area.size_hint_y == 0.10
    assert app.header_area.opacity == 1


def test_android_element_summary_omits_voltage_and_keeps_required_fields():
    app = SubstationAndroidApp()
    element = {
        "serial_number": "SN-100",
        "manufacturer": "Siemens",
        "model_name": "Model A",
        "manufacture_year": "2020",
        "maintenance_cycle": 12,
        "maintenance_date": "2024-06-10",
        "voltage_level": "20kV",
        "power_mva": 12.5,
        "element_type": "Διακόπτης ΜΤ",
        "model_manufacturer": "Siemens",
        "operations_count": 44,
    }

    summary = app._build_element_summary_text(element)

    assert "S/N: SN-100" in summary
    assert "Κατ.: Siemens" in summary
    assert "Μοντ.: Model A" in summary
    assert "Έτος: 2020" in summary
    assert "Κύκλος: 12" in summary
    assert "Τελ. Συντ.: 2024-06-10" in summary
    assert "Αριθμός Χειρισμών: 44" in summary
    assert "20kV" not in summary


def test_android_element_detail_lines_include_full_metadata():
    app = SubstationAndroidApp()
    element = {
        "name": "Q1",
        "element_type": "Διακόπτης ΜΤ",
        "serial_number": "SN-100",
        "manufacturer": "Siemens",
        "model_name": "Model A",
        "model_manufacturer": "Siemens",
        "manufacture_year": "2020",
        "installation_space": "Εσωτερικός",
        "maintenance_date": "2024-06-10",
        "maintenance_cycle": 12,
        "voltage_level": "20kV",
        "power_mva": 12.5,
        "breaker_category": "SF6",
        "vector_group": "Yd",
        "operations_count": 44,
    }

    lines = app._build_element_detail_lines(element)
    joined = "\n".join(lines)

    assert "Χώρος: Εσωτερικός" in joined
    assert "Τάση: 20kV" in joined
    assert "Ονομαστική Ισχύς: 12.5" in joined
    assert "Κατηγορία Διακόπτη: SF6" in joined
    assert "Κύκλος: 12" in joined


def test_android_quick_view_close_button_dismisses_popup(monkeypatch):
    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return (
                "Q1",
                "????????? ??",
                "SN-100",
                12.5,
                "Siemens",
                "2020",
                "??????????",
                "2024-06-10",
                3,
                44,
                "Yd",
                "SF6",
                12,
                "Model A",
                "Siemens",
                "??????????",
                12.5,
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
                None,
                None,
                "20kV",
                "Model A",
            )

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            return None

    class FakePopup:
        def __init__(self, *args, **kwargs):
            self.content = None
            self.dismissed = False
            self.opened = False

        def open(self):
            self.opened = True

        def dismiss(self, *args, **kwargs):
            self.dismissed = True

    class FakeButton:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            self.bindings = {}

        def bind(self, **kwargs):
            self.bindings.update(kwargs)

    class FakeBoxLayout:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.height = 0

        @staticmethod
        def setter(prop):
            def _assign(obj, value):
                setattr(obj, prop, value)

            return _assign

        def add_widget(self, widget):
            self.children.append(widget)

        def bind(self, **kwargs):
            return None

    class FakeScrollView(FakeBoxLayout):
        pass

    class FakeLabel:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    captured = {}

    def fake_popup(*args, **kwargs):
        obj = FakePopup(*args, **kwargs)
        captured["popup"] = obj
        return obj

    monkeypatch.setattr("android_app.Popup", fake_popup)
    monkeypatch.setattr("android_app.Button", FakeButton)
    monkeypatch.setattr("android_app.BoxLayout", FakeBoxLayout)
    monkeypatch.setattr("android_app.ScrollView", FakeScrollView)
    monkeypatch.setattr("android_app.Label", FakeLabel)
    monkeypatch.setattr(
        "android_app.sqlite3.connect", lambda *args, **kwargs: FakeConnection()
    )

    app = SubstationAndroidApp()
    app.local_db_path = "dummy.db"
    app._show_element_quick_view(1)

    close_btn = captured["popup"].content.children[0].children[-1]
    close_btn.bindings["on_press"](close_btn)
    assert captured["popup"].dismissed is True
