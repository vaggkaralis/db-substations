from email_eml_parser import sanitize_email_body_for_import
from email.message import EmailMessage
from pathlib import Path

from email_eml_parser import parse_eml_file


def test_sanitize_removes_embedded_forwarded_headers_and_recipients():
    body = (
        "Καλησπέρα! Σήμερα στον ΥΣ Αμφίπολης εκτελέστηκαν εργασίες.\n\n"
        "From: Γεωργίου Λάζαρος\n"
        "Sent: Tuesday, October 21, 2025 9:02:55 PM\n"
        "Το: Παπαδοπούλου Μαρία <m@example.com>; Καραλής Ευάγγελος <e@example.com>\n"
        "Cc: Παπασπύρου Σπύρος <s@example.com>\n"
        "Subject: Αναφορά συνεργείου ...\n"
        "Παλαιότερο περιεχόμενο μηνύματος"
    )

    cleaned = sanitize_email_body_for_import(body)

    assert "Καλησπέρα!" in cleaned
    assert "From:" not in cleaned
    assert "Sent:" not in cleaned
    assert "Το:" not in cleaned
    assert "Cc:" not in cleaned
    assert "Subject:" not in cleaned
    assert "Παπαδοπούλου" not in cleaned
    assert "Καραλής" not in cleaned
    assert "Παλαιότερο περιεχόμενο" not in cleaned


def test_sanitize_skips_initial_header_block_then_keeps_body():
    body = (
        "From: sender@example.com\n"
        "Date: Tue, 21 Oct 2025 21:02:55 +0300\n"
        "To: someone@example.com\n"
        "Subject: Αναφορά\n\n"
        "Κύριο κείμενο πρώτου μηνύματος."
    )

    cleaned = sanitize_email_body_for_import(body)

    assert cleaned == "Κύριο κείμενο πρώτου μηνύματος."


def test_sanitize_preserves_readable_newlines_for_numbered_steps():
    body = (
        "Καλησπέρα! Σήμερα εκτελέστηκαν οι εργασίες: "
        "1. Λήψη αδειών εργασίας. 2. Τοποθέτηση γειώσεων. "
        "3. Συντήρηση διακοπτών. Σημείωση 1η: Χρειάζεται ενημέρωση ΑΔΜΗΕ."
    )

    cleaned = sanitize_email_body_for_import(body)

    assert "\n1. Λήψη αδειών εργασίας." in cleaned
    assert "\n2. Τοποθέτηση γειώσεων." in cleaned
    assert "\n3. Συντήρηση διακοπτών." in cleaned
    assert "\nΣημείωση 1η:" in cleaned


def test_parse_eml_file_uses_same_sanitization(tmp_path: Path):
    msg = EmailMessage()
    msg["Subject"] = "Test"
    msg["From"] = "Sender <sender@example.com>"
    msg["To"] = "Recipient <recipient@example.com>"
    msg.set_content(
        "Καλησπέρα! 1. Πρώτο βήμα. 2. Δεύτερο βήμα.\n\n"
        "From: Old Sender\n"
        "To: Παπαδοπούλου Μαρία <m@example.com>\n"
        "Subject: old\n"
        "Παλαιό μήνυμα"
    )

    eml_path = tmp_path / "sample.eml"
    eml_path.write_bytes(msg.as_bytes())

    parsed = parse_eml_file(str(eml_path))
    body = parsed["body"]

    assert "From:" not in body
    assert "To:" not in body
    assert "Παπαδοπούλου" not in body
    assert "\n1. Πρώτο βήμα." in body
    assert "\n2. Δεύτερο βήμα." in body


def test_parse_eml_file_strips_html_markup_from_text_plain_part(tmp_path: Path):
    html_body = (
        "<html><body>"
        "<p>Καλημέρα σας.</p>"
        "<p>Αίτηση απομόνωσης του Υ/Σ ΙΑΣΜΟΥ για 11/5 και ώρα 09.00 έως 13.00.</p>"
        "<p>Θεσσαλονίκη 54632</p>"
        "</body></html>"
    )

    msg = EmailMessage()
    msg["Subject"] = "Isolation"
    msg["From"] = "Sender <sender@example.com>"
    msg["To"] = "Recipient <recipient@example.com>"
    msg.set_content(html_body, charset="utf-8")

    eml_path = tmp_path / "html_in_plain_part.eml"
    eml_path.write_bytes(msg.as_bytes())

    parsed = parse_eml_file(str(eml_path))

    assert "<html" not in parsed["body"].lower()
    assert "11/5" in parsed["body"]
    assert "09.00" in parsed["body"]
    assert "54632" in parsed["body"]


def test_parse_eml_file_keeps_7z_attachment(tmp_path: Path):
    msg = EmailMessage()
    msg["Subject"] = "Archive"
    msg["From"] = "Sender <sender@example.com>"
    msg["To"] = "Recipient <recipient@example.com>"
    msg.set_content("Δες το συνημμένο αρχείο.")
    msg.add_attachment(
        b"7z-bytes",
        maintype="application",
        subtype="x-7z-compressed",
        filename="reports.7z",
    )

    eml_path = tmp_path / "archive.eml"
    eml_path.write_bytes(msg.as_bytes())

    parsed = parse_eml_file(str(eml_path))

    assert len(parsed["attachment_paths"]) == 1
    assert parsed["attachment_paths"][0].lower().endswith("reports.7z")
