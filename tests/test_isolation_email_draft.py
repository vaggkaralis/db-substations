import os
import sys
import types

from isolation_ui import (
    _build_isolation_email_body,
    _build_isolation_email_subject,
    _create_outlook_isolation_draft,
    _extract_email_addresses,
    _pick_template_xlsx_attachment,
)


def test_extract_email_addresses_deduplicates_and_keeps_order():
    raw = "User One <one@example.com>, two@example.com, User One <one@example.com>"
    assert _extract_email_addresses(raw) == ["one@example.com", "two@example.com"]


def test_pick_template_xlsx_attachment_returns_existing_xlsx(tmp_path):
    xlsx_file = tmp_path / "request.xlsx"
    xlsx_file.write_bytes(b"dummy")
    payload = {
        "document_attachment_paths": [
            str(tmp_path / "note.txt"),
            str(xlsx_file),
        ]
    }
    assert _pick_template_xlsx_attachment(payload) == str(xlsx_file)


def test_build_isolation_email_content_contains_db_data():
    subject = _build_isolation_email_subject(
        request_id=42,
        substation_name="SUB_A",
        template_payload={"subject": "Template Subject"},
    )
    body = _build_isolation_email_body(
        request_id=42,
        substation_name="SUB_A",
        start_dt="2026-06-26 09:30",
        end_dt="2026-06-26 12:30",
        notes="Important note",
        selected_elements=[("E1", "TR", "GATE_1")],
    )

    assert "Template Subject" in subject
    assert "#42" in subject
    assert "SUB_A" in body
    assert "2026-06-26 09:30" in body
    assert "2026-06-26 12:30" in body
    assert "Important note" in body
    assert "E1" in body


def test_create_outlook_isolation_draft_success(monkeypatch, tmp_path):
    attachment = tmp_path / "request.xlsx"
    attachment.write_bytes(b"dummy")
    template_eml = tmp_path / "template.eml"
    template_eml.write_text("dummy", encoding="utf-8")

    class DummyAttachments:
        def __init__(self):
            self.added = []
            self.removed = []
            self.Count = 1

        def Add(self, path):
            self.added.append(path)

        def Remove(self, index):
            self.removed.append(index)

    class DummyMail:
        def __init__(self):
            self.To = ""
            self.CC = ""
            self.Subject = ""
            self.Body = ""
            self.Attachments = DummyAttachments()
            self.displayed = False

        def Display(self, _modal):
            self.displayed = True

    class DummyNamespace:
        def __init__(self):
            self.opened_path = None
            self.opened_item = None

        def OpenSharedItem(self, path):
            self.opened_path = path
            self.opened_item = DummyMail()
            return self.opened_item

    class DummyOutlook:
        def __init__(self):
            self.last_item = None
            self.namespace = DummyNamespace()

        def CreateItem(self, _kind):
            self.last_item = DummyMail()
            return self.last_item

        def GetNamespace(self, _name):
            return self.namespace

    dummy_outlook = DummyOutlook()

    win32com_module = types.ModuleType("win32com")
    win32com_client_module = types.ModuleType("win32com.client")
    win32com_client_module.Dispatch = lambda _name: dummy_outlook
    win32com_module.client = win32com_client_module

    monkeypatch.setitem(sys.modules, "win32com", win32com_module)
    monkeypatch.setitem(sys.modules, "win32com.client", win32com_client_module)

    ok, msg = _create_outlook_isolation_draft(
        template_payload={
            "headers": {
                "to": "A <a@example.com>, b@example.com",
                "cc": "C <c@example.com>",
            },
            "_template_eml_path": str(template_eml),
        },
        subject="Subj",
        body="Body",
        attachment_path=str(attachment),
    )

    assert ok is True
    assert msg == ""
    # OpenSharedItem path is preferred when template .eml exists.
    assert dummy_outlook.namespace.opened_path == str(template_eml)
    # CreateItem fallback should not be used in this case.
    assert dummy_outlook.last_item is None
    opened_item = dummy_outlook.namespace.opened_item
    assert opened_item is not None
    assert opened_item.To == "a@example.com;b@example.com"
    assert opened_item.CC == "c@example.com"
    assert opened_item.Subject == "Subj"
    assert opened_item.Body == "Body"
    assert opened_item.displayed is True
    assert opened_item.Attachments.removed == [1]
    assert len(opened_item.Attachments.added) == 1
    assert os.path.abspath(str(attachment)) == opened_item.Attachments.added[0]


def test_create_outlook_isolation_draft_requires_to_recipients(tmp_path):
    attachment = tmp_path / "request.xlsx"
    attachment.write_bytes(b"dummy")

    ok, msg = _create_outlook_isolation_draft(
        template_payload={"headers": {"to": ""}},
        subject="Subj",
        body="Body",
        attachment_path=str(attachment),
    )

    assert ok is False
    assert "To" in msg
