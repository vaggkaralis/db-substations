import os

import DBrun


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
    monkeypatch.setattr(DBrun, "ScrollView", DummyWidget)
    monkeypatch.setattr(DBrun, "Label", DummyLabel)
    monkeypatch.setattr(DBrun, "Button", DummyButton)
    monkeypatch.setattr(DBrun, "Popup", DummyPopup)
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
    review_button = None
    for child in popup.content.children:
        for grandchild in getattr(child, "children", []):
            if getattr(grandchild, "text", "") == DBrun.S["BUTTONS"].get(
                "VIEW", "Review"
            ):
                review_button = grandchild
                break
        if review_button is not None:
            break

    assert review_button is not None
    review_button.trigger("on_press")

    assert captured.get("maintenance_called") is not True
    assert captured["status"] == "Requested"
    assert captured["isolation_payload"]["attachment_paths"] == ["req.xlsx"]
    assert callable(captured["after_save_callback"])


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
