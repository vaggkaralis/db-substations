import os

import DBrun


class _DummyCursor:
    def __init__(self, rows=None):
        self._source_rows = list(rows or [])
        self._rows = list(self._source_rows)

    def execute(self, query, _params=None):
        if "SELECT id, name FROM substations" in query:
            self._rows = list(self._source_rows)
            return None
        self._rows = []

    def fetchall(self):
        return list(self._rows)


class _DummyConn:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def cursor(self):
        return _DummyCursor(self._rows)


def _find_widget_by_text(root, text):
    if getattr(root, "text", "") == text:
        return root
    for child in getattr(root, "children", []):
        found = _find_widget_by_text(child, text)
        if found is not None:
            return found
    return None


def _collect_texts(root):
    texts = []
    text = getattr(root, "text", "")
    if text:
        texts.append(text)
    for child in getattr(root, "children", []):
        texts.extend(_collect_texts(child))
    return texts


def test_list_pending_startup_report_eml_files_filters_top_level_eml_files(tmp_path):
    first = tmp_path / "B_report.eml"
    first.write_text("b", encoding="utf-8")
    second = tmp_path / "a_report.EML"
    second.write_text("a", encoding="utf-8")
    ignored = tmp_path / "notes.txt"
    ignored.write_text("ignore", encoding="utf-8")
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_eml = nested_dir / "nested.eml"
    nested_eml.write_text("nested", encoding="utf-8")

    files = DBrun.SubstationApp._list_pending_startup_report_eml_files(str(tmp_path))

    assert files == [str(second.resolve()), str(first.resolve())]
    assert str(nested_eml.resolve()) not in files


def test_delete_startup_report_source_file_removes_source_and_temp_attachments(
    tmp_path,
):
    app = object.__new__(DBrun.SubstationApp)
    app.conn = _DummyConn()
    source_file = tmp_path / "report.eml"
    source_file.write_text("report", encoding="utf-8")

    attachment_dir = tmp_path / "eml_media_case"
    attachment_dir.mkdir()
    attachment_path = attachment_dir / "photo.jpg"
    attachment_path.write_text("photo", encoding="utf-8")

    payload = {"attachment_paths": [str(attachment_path)]}

    removed = app._delete_startup_report_source_file(str(source_file), payload=payload)

    assert removed is True
    assert not source_file.exists()
    assert not attachment_path.exists()
    assert not os.path.exists(attachment_dir)


def test_get_pending_startup_review_items_includes_reports_and_isolations(
    monkeypatch, tmp_path
):
    app = object.__new__(DBrun.SubstationApp)
    app.db_path = str(tmp_path / "app.sqlite")

    sync_root = tmp_path / "sync_root"
    reports_dir = sync_root / "reports"
    isolations_dir = sync_root / "isolations"
    reports_dir.mkdir(parents=True)
    isolations_dir.mkdir(parents=True)

    report_file = reports_dir / "maintenance.eml"
    report_file.write_text("report", encoding="utf-8")
    isolation_file = isolations_dir / "isolation.eml"
    isolation_file.write_text("iso", encoding="utf-8")

    monkeypatch.setattr(
        "sync_service.resolve_sync_root", lambda _db_path: str(sync_root)
    )

    items = app._get_pending_startup_review_items()

    assert items == [
        {
            "kind": "maintenance",
            "source_folder": "reports",
            "file_path": str(report_file.resolve()),
        },
        {
            "kind": "isolation",
            "source_folder": "isolations",
            "file_path": str(isolation_file.resolve()),
        },
    ]


def test_startup_review_popup_routes_isolation_items_to_isolation_import(
    monkeypatch, tmp_path
):
    captured = {}

    class DummyWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.text = kwargs.get("text", "")
            self._callbacks = {}

        def add_widget(self, widget):
            self.children.append(widget)

        def bind(self, **kwargs):
            self._callbacks.update(kwargs)

        def setter(self, attr_name):
            return lambda _instance, value: setattr(self, attr_name, value)

        def remove_widget(self, widget):
            if widget in self.children:
                self.children.remove(widget)

    class DummyLabel(DummyWidget):
        width = 100

    class DummyButton(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.disabled = False

        def trigger(self, event_name):
            callback = self._callbacks.get(event_name)
            if callback:
                callback(self)

    class DummyPopup(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.title = kwargs.get("title")
            self.size_hint = kwargs.get("size_hint")
            self.auto_dismiss = kwargs.get("auto_dismiss", True)
            self.content = None
            captured.setdefault("popups", []).append(self)

        def open(self):
            captured["opened_popup"] = self

        def dismiss(self):
            callback = self._callbacks.get("on_dismiss")
            if callback:
                callback(self)

    monkeypatch.setattr(DBrun, "BoxLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "GridLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "ScrollView", DummyWidget)
    monkeypatch.setattr(DBrun, "Label", DummyLabel)
    monkeypatch.setattr(DBrun, "Button", DummyButton)
    monkeypatch.setattr(DBrun, "Popup", DummyPopup)
    monkeypatch.setattr(DBrun, "Widget", DummyWidget)
    monkeypatch.setattr(
        DBrun,
        "parse_eml_file",
        lambda _path: {
            "subject": "Isolation request",
            "sender_name": "Operator",
            "received_at": "2026-05-05 09:00",
            "attachment_paths": ["req.xlsx"],
        },
    )

    app = object.__new__(DBrun.SubstationApp)
    app.conn = _DummyConn()

    def _open_isolation(payload, status="Requested", after_save_callback=None):
        captured["isolation_payload"] = payload
        captured["status"] = status
        captured["after_save_callback"] = after_save_callback

    app._open_isolation_from_email_payload = _open_isolation
    app._open_maintenance_from_email_payload = lambda *args, **kwargs: captured.update(
        {"maintenance_called": True}
    )

    isolation_file = tmp_path / "isolation.eml"
    isolation_file.write_text("eml", encoding="utf-8")

    shown = app._show_startup_report_review_popup(
        [
            {
                "kind": "isolation",
                "source_folder": "isolations",
                "file_path": str(isolation_file),
            }
        ]
    )

    assert shown is True

    popup = captured["opened_popup"]
    review_button = _find_widget_by_text(
        popup.content, DBrun.S["BUTTONS"].get("VIEW", "Review")
    )

    assert review_button is not None
    review_button.trigger("on_press")

    assert captured.get("maintenance_called") is not True
    assert captured["status"] == "Requested"
    assert captured["isolation_payload"]["attachment_paths"] == ["req.xlsx"]
    assert callable(captured["after_save_callback"])


def test_startup_review_popup_uses_isolation_match_for_isolation_title(
    monkeypatch, tmp_path
):
    import isolation_importer

    captured = {}

    class DummyWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.text = kwargs.get("text", "")
            self._callbacks = {}

        def add_widget(self, widget):
            self.children.append(widget)

        def bind(self, **kwargs):
            self._callbacks.update(kwargs)

        def setter(self, attr_name):
            return lambda _instance, value: setattr(self, attr_name, value)

        def remove_widget(self, widget):
            if widget in self.children:
                self.children.remove(widget)

    class DummyLabel(DummyWidget):
        width = 100

    class DummyButton(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.disabled = False

    class DummyPopup(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.title = kwargs.get("title")
            self.size_hint = kwargs.get("size_hint")
            self.auto_dismiss = kwargs.get("auto_dismiss", True)
            self.content = None
            captured["popup"] = self

        def open(self):
            captured["opened_popup"] = self

        def dismiss(self):
            callback = self._callbacks.get("on_dismiss")
            if callback:
                callback(self)

    monkeypatch.setattr(DBrun, "BoxLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "GridLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "ScrollView", DummyWidget)
    monkeypatch.setattr(DBrun, "Label", DummyLabel)
    monkeypatch.setattr(DBrun, "Button", DummyButton)
    monkeypatch.setattr(DBrun, "Popup", DummyPopup)
    monkeypatch.setattr(DBrun, "Widget", DummyWidget)
    monkeypatch.setattr(
        DBrun,
        "parse_eml_file",
        lambda _path: {
            "subject": "",
            "sender_name": "Operator",
            "received_at": "2026-05-05T09:00:00+00:00",
            "body": "Απομόνωση του Υ/Σ ΙΑΣΜΟΥ. Υπογραφή: Θεσσαλονίκη 54632.",
            "attachment_paths": [],
        },
    )
    monkeypatch.setattr(
        isolation_importer,
        "match_substation",
        lambda _app, _text, _substations: (23, "ΙΑΣΜΟΣ"),
    )

    app = object.__new__(DBrun.SubstationApp)
    app.conn = _DummyConn([(23, "ΙΑΣΜΟΣ"), (26, "ΘΕΣΣΑΛΟΝΙΚΗ III (ΑΓ.ΔΗΜΗΤΡΙΟΣ)")])
    app._find_substation_in_text = lambda _text, substations: substations[1]
    app._open_isolation_from_email_payload = lambda *args, **kwargs: None
    app._open_maintenance_from_email_payload = lambda *args, **kwargs: None

    isolation_file = tmp_path / "iasmos.eml"
    isolation_file.write_text("eml", encoding="utf-8")

    shown = app._show_startup_report_review_popup(
        [
            {
                "kind": "isolation",
                "source_folder": "isolations",
                "file_path": str(isolation_file),
            }
        ]
    )

    assert shown is True
    texts = _collect_texts(captured["opened_popup"].content)
    assert any("ΙΑΣΜΟΣ" in text for text in texts)
    assert not any("ΘΕΣΣΑΛΟΝΙΚΗ III" in text for text in texts)


def test_startup_review_popup_groups_maintenance_attachments_and_reopens_on_cancel(
    monkeypatch, tmp_path
):
    captured = {}

    class DummyWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.text = kwargs.get("text", "")
            self._callbacks = {}

        def add_widget(self, widget):
            self.children.append(widget)

        def bind(self, **kwargs):
            self._callbacks.update(kwargs)

        def setter(self, attr_name):
            return lambda _instance, value: setattr(self, attr_name, value)

        def remove_widget(self, widget):
            if widget in self.children:
                self.children.remove(widget)

    class DummyLabel(DummyWidget):
        width = 100

    class DummyButton(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.disabled = False

        def trigger(self, event_name):
            callback = self._callbacks.get(event_name)
            if callback:
                callback(self)

    class DummyPopup(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.title = kwargs.get("title")
            self.size_hint = kwargs.get("size_hint")
            self.auto_dismiss = kwargs.get("auto_dismiss", True)
            self.content = None
            captured.setdefault("popups", []).append(self)

        def open(self):
            captured["opened_popup"] = self

        def dismiss(self):
            callback = self._callbacks.get("on_dismiss")
            if callback:
                callback(self)

    parse_map = {}

    def _parse_eml(path):
        return parse_map[str(path)]

    monkeypatch.setattr(DBrun, "BoxLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "GridLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "ScrollView", DummyWidget)
    monkeypatch.setattr(DBrun, "Label", DummyLabel)
    monkeypatch.setattr(DBrun, "Button", DummyButton)
    monkeypatch.setattr(DBrun, "Popup", DummyPopup)
    monkeypatch.setattr(DBrun, "Widget", DummyWidget)
    monkeypatch.setattr(DBrun, "parse_eml_file", _parse_eml)
    monkeypatch.setattr(
        DBrun.Clock, "schedule_once", lambda callback, _dt=0: callback(0)
    )

    app = object.__new__(DBrun.SubstationApp)
    app.conn = _DummyConn([(1, "ΝΑΟΥΣΑ")])
    app._startup_review_deferred_paths = set()
    app._find_substation_in_text = lambda _text, substations: substations[0]
    app._get_pending_startup_review_items = lambda: [
        {
            "kind": "maintenance",
            "source_folder": "reports",
            "file_path": str(first_file),
        },
        {
            "kind": "maintenance",
            "source_folder": "reports",
            "file_path": str(second_file),
        },
    ]
    app._open_isolation_from_email_payload = lambda *args, **kwargs: None

    def _open_maintenance(
        payload,
        forced_substation=None,
        after_save_callback=None,
        after_cancel_callback=None,
    ):
        captured["maintenance_payload"] = payload
        captured["after_save_callback"] = after_save_callback
        captured["after_cancel_callback"] = after_cancel_callback

    app._open_maintenance_from_email_payload = _open_maintenance

    first_file = tmp_path / "naousa-1.eml"
    second_file = tmp_path / "naousa-2.eml"
    first_file.write_text("1", encoding="utf-8")
    second_file.write_text("2", encoding="utf-8")

    parse_map[str(first_file)] = {
        "subject": "Συντήρηση ΜΣ1 Υ/Σ Νάουσας 06.05.2026",
        "sender_name": "Operator",
        "received_at": "2026-05-06T09:00:00+00:00",
        "attachment_paths": ["first-a.pdf", "shared.xlsx"],
        "headers": {"thread_topic": "Συντήρηση ΜΣ1 Υ/Σ Νάουσας"},
    }
    parse_map[str(second_file)] = {
        "subject": "Re: Συντήρηση ΜΣ1 Υ/Σ Νάουσας 07.05.2026",
        "sender_name": "Operator",
        "received_at": "2026-05-07T09:00:00+00:00",
        "attachment_paths": ["second-b.pdf", "shared.xlsx"],
        "headers": {"thread_topic": "Συντήρηση ΜΣ1 Υ/Σ Νάουσας"},
    }

    shown = app._show_startup_report_review_popup(
        [
            {
                "kind": "maintenance",
                "source_folder": "reports",
                "file_path": str(first_file),
            },
            {
                "kind": "maintenance",
                "source_folder": "reports",
                "file_path": str(second_file),
            },
        ]
    )

    assert shown is True

    popup = captured["opened_popup"]
    review_button = _find_widget_by_text(
        popup.content, DBrun.S["BUTTONS"].get("VIEW", "Review")
    )

    assert review_button is not None
    review_button.trigger("on_press")

    assert captured["maintenance_payload"]["attachment_paths"] == [
        "first-a.pdf",
        "shared.xlsx",
        "second-b.pdf",
    ]
    assert callable(captured["after_cancel_callback"])

    popup_count_before_cancel = len(captured["popups"])
    captured["after_cancel_callback"]()
    assert len(captured["popups"]) == popup_count_before_cancel + 1


def test_startup_review_popup_groups_three_maintenance_emails_including_older_one(
    monkeypatch, tmp_path
):
    captured = {}

    class DummyWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.text = kwargs.get("text", "")
            self._callbacks = {}

        def add_widget(self, widget):
            self.children.append(widget)

        def bind(self, **kwargs):
            self._callbacks.update(kwargs)

        def setter(self, attr_name):
            return lambda _instance, value: setattr(self, attr_name, value)

        def remove_widget(self, widget):
            if widget in self.children:
                self.children.remove(widget)

    class DummyLabel(DummyWidget):
        width = 100

    class DummyButton(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.disabled = False

        def trigger(self, event_name):
            callback = self._callbacks.get(event_name)
            if callback:
                callback(self)

    class DummyPopup(DummyWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.title = kwargs.get("title")
            self.size_hint = kwargs.get("size_hint")
            self.auto_dismiss = kwargs.get("auto_dismiss", True)
            self.content = None
            captured.setdefault("popups", []).append(self)

        def open(self):
            captured["opened_popup"] = self

        def dismiss(self):
            callback = self._callbacks.get("on_dismiss")
            if callback:
                callback(self)

    parse_map = {}

    def _parse_eml(path):
        return parse_map[str(path)]

    monkeypatch.setattr(DBrun, "BoxLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "GridLayout", DummyWidget)
    monkeypatch.setattr(DBrun, "ScrollView", DummyWidget)
    monkeypatch.setattr(DBrun, "Label", DummyLabel)
    monkeypatch.setattr(DBrun, "Button", DummyButton)
    monkeypatch.setattr(DBrun, "Popup", DummyPopup)
    monkeypatch.setattr(DBrun, "Widget", DummyWidget)
    monkeypatch.setattr(DBrun, "parse_eml_file", _parse_eml)

    app = object.__new__(DBrun.SubstationApp)
    app.conn = _DummyConn([(1, "ΝΑΟΥΣΑ")])
    app._startup_review_deferred_paths = set()
    app._find_substation_in_text = lambda _text, substations: substations[0]
    app._open_isolation_from_email_payload = lambda *args, **kwargs: None

    def _open_maintenance(
        payload,
        forced_substation=None,
        after_save_callback=None,
        after_cancel_callback=None,
    ):
        captured["maintenance_payload"] = payload

    app._open_maintenance_from_email_payload = _open_maintenance

    file_06 = tmp_path / "naousa-06.eml"
    file_07 = tmp_path / "naousa-07.eml"
    file_05 = tmp_path / "naousa-05.eml"
    file_06.write_text("06", encoding="utf-8")
    file_07.write_text("07", encoding="utf-8")
    file_05.write_text("05", encoding="utf-8")

    parse_map[str(file_06)] = {
        "subject": "Συντήρηση ΜΣ1 Υ/Σ Νάουσας 06.05.2026",
        "sender_name": "Operator",
        "received_at": "2026-05-06T17:36:32+00:00",
        "body": "Εργασίες 6/5.",
        "attachment_paths": ["six-a.pdf", "shared.xlsx"],
        "headers": {"thread_topic": "Συντήρηση ΜΣ1 Υ/Σ Νάουσας"},
    }
    parse_map[str(file_07)] = {
        "subject": "Re: Συντήρηση ΜΣ1 Υ/Σ Νάουσας 07.05.2026",
        "sender_name": "Operator",
        "received_at": "2026-05-07T11:24:56+00:00",
        "body": "Εργασίες 7/5.",
        "attachment_paths": [],
        "headers": {"thread_topic": "Συντήρηση ΜΣ1 Υ/Σ Νάουσας"},
    }
    parse_map[str(file_05)] = {
        "subject": "Re: Συντήρηση ΜΣ1 Υ/Σ Νάουσας 05.05.2026",
        "sender_name": "Operator",
        "received_at": "2026-05-05T17:02:35+00:00",
        "body": "Εργασίες 5/5.",
        "attachment_paths": ["five-a.pdf", "shared.xlsx"],
        "headers": {"thread_topic": "Συντήρηση ΜΣ1 Υ/Σ Νάουσας"},
    }

    shown = app._show_startup_report_review_popup(
        [
            {
                "kind": "maintenance",
                "source_folder": "reports",
                "file_path": str(file_06),
            },
            {
                "kind": "maintenance",
                "source_folder": "reports",
                "file_path": str(file_07),
            },
            {
                "kind": "maintenance",
                "source_folder": "reports",
                "file_path": str(file_05),
            },
        ]
    )

    assert shown is True

    popup = captured["opened_popup"]
    review_button = _find_widget_by_text(
        popup.content, DBrun.S["BUTTONS"].get("VIEW", "Review")
    )

    assert review_button is not None
    review_button.trigger("on_press")

    body = captured["maintenance_payload"]["body"]
    assert "5/5/2026\nΕργασίες 5/5." in body
    assert "6/5/2026\nΕργασίες 6/5." in body
    assert "7/5/2026\nΕργασίες 7/5." in body
    assert captured["maintenance_payload"]["attachment_paths"] == [
        "five-a.pdf",
        "shared.xlsx",
        "six-a.pdf",
    ]


def test_calculate_expanding_text_input_height_does_not_cap_long_grouped_comments():
    grouped_comments = "\n".join(f"line {index}" for index in range(48))

    height = DBrun._calculate_expanding_text_input_height(grouped_comments, 180)

    assert height == 24 * 48 + 20
    assert height > 1000


def test_isolation_payload_import_forwards_after_save_callback(monkeypatch):
    import isolation_ui

    captured = {}

    def callback():
        return None

    def _prefill(
        app,
        parent_popup,
        raw_text,
        status,
        attachment_paths=None,
        after_save_callback=None,
    ):
        captured["raw_text"] = raw_text
        captured["status"] = status
        captured["attachment_paths"] = attachment_paths
        captured["after_save_callback"] = after_save_callback

    monkeypatch.setattr(isolation_ui, "_prefill_imported_isolation", _prefill)

    isolation_ui.import_isolation_request_from_payload(
        object(),
        {"body": "body text", "attachment_paths": ["req.xlsx"]},
        status="Requested",
        after_save_callback=callback,
    )

    assert captured["raw_text"] == "body text"
    assert captured["status"] == "Requested"
    assert captured["attachment_paths"] == ["req.xlsx"]
    assert captured["after_save_callback"] is callback
