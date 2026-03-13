"""
Parse .pdf files and return normalized fields compatible with maintenance email import.

The returned dict has the same keys as parse_eml_file() so it can be fed directly
into create_maintenance_from_email() / open_maintenance_from_email_payload().

PDFs that are Outlook email exports contain an embedded header block:
    Από: <name>
    <email address>
    Προς: ...
    Eστάλη: <date>
This module detects that pattern and extracts sender, date and body correctly,
so the downstream importer sees the same data it would get from a real EML file.
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Suppress noisy pdfminer font-parsing warnings (FontBBox, etc.)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# Patterns for detecting Outlook-email-export headers embedded in PDF text
# ---------------------------------------------------------------------------

# Greek / English "From:" header line
_RE_FROM = re.compile(r"^\s*(?:Από|From)\s*:\s*(.+)$", re.IGNORECASE)
# Greek "Sent:" header line (Εστάλη / Eστάλη / Στάλθηκε) or English "Sent:"
_RE_SENT = re.compile(
    r"^\s*(?:Eστάλη|Εστάλη|Στάλθηκε|Sent)\s*:\s*(.+)$", re.IGNORECASE
)
# A bare email address on its own line (after the "Από:" line)
_RE_EMAIL = re.compile(r"^\s*[\w.+\-]+@[\w.\-]+\.[a-z]{2,}\s*$", re.IGNORECASE)
# "Στάλθηκε από Outlook" or "Sent from Outlook" — marks the forwarded-quote block
_RE_SENT_FROM = re.compile(
    r"^\s*(?:Στάλθηκε από|Sent from)\b", re.IGNORECASE
)
# "From:" in the forwarded-quote block that ends the relevant content
_RE_FROM_QUOTE = re.compile(r"^\s*From\s*:\s*", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    """Replace typographic whitespace variants with plain ASCII equivalents."""
    # \u202f = NARROW NO-BREAK SPACE, \xa0 = NO-BREAK SPACE
    return text.replace("\u202f", " ").replace("\xa0", " ")


def _parse_email_headers(lines: list[str]) -> dict:
    """Scan lines for embedded Outlook header block and return extracted fields.

    Returns a dict with keys:
        sender_name, sender_email, received_at (ISO str or None),
        body_start_index (int – line index where the actual body begins)
    """
    sender_name: str | None = None
    sender_email: str | None = None
    received_at: str | None = None
    body_start_index: int = 0

    from_idx: int | None = None
    sent_idx: int | None = None

    for i, line in enumerate(lines):
        m = _RE_FROM.match(line)
        if m and from_idx is None:
            sender_name = m.group(1).strip()
            from_idx = i
            # The very next non-empty line may be the email address
            for j in range(i + 1, min(i + 4, len(lines))):
                if _RE_EMAIL.match(lines[j]):
                    sender_email = lines[j].strip()
                    break
            continue

        m = _RE_SENT.match(line)
        if m and from_idx is not None and sent_idx is None:
            sent_idx = i
            raw_date = m.group(1).strip()
            # Try to parse Greek date patterns: "Τετάρτη 1 Μαΐου στις 4:50 μ.μ."
            received_at = _parse_greek_date(raw_date)
            # Body starts after the next blank line following Eστάλη:
            for j in range(i + 1, min(i + 6, len(lines))):
                if not lines[j].strip():
                    body_start_index = j + 1
                    break
            else:
                body_start_index = i + 1
            break

    return {
        "sender_name": sender_name,
        "sender_email": sender_email,
        "received_at": received_at,
        "body_start_index": body_start_index,
    }


# Greek month names → month number
_GREEK_MONTHS = {
    "ιανουαρ": 1,  "φεβρουαρ": 2, "μαρτ": 3,   "απριλ": 4,
    "μαΐου": 5,    "μαιου": 5,    "ιουν": 6,    "ιουλ": 7,
    "αυγ": 8,      "σεπτ": 9,     "οκτ": 10,    "νοεμβρ": 11,
    "δεκεμβρ": 12,
}

def _parse_greek_date(raw: str) -> str | None:
    """Attempt to parse a Greek date string into ISO-8601 UTC.

    Handles patterns like:
      'Τετάρτη 1 Μαΐου στις 4:50 μ.μ.'
      '1/5/2024'   '01-05-2024'
    Returns ISO string or None on failure.
    """
    raw = raw.strip()

    # Try numeric date: dd/mm/yyyy or similar
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", raw)
    if m:
        try:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            dt = datetime(y, mo, d, tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    # Try Greek month name: "1 Μαΐου" or "Μαΐου 2024"
    raw_lower = raw.lower()
    for stem, month_num in _GREEK_MONTHS.items():
        if stem in raw_lower:
            day_m = re.search(r"\b(\d{1,2})\b", raw)
            year_m = re.search(r"\b(20\d{2})\b", raw)
            day = int(day_m.group(1)) if day_m else 1
            year = int(year_m.group(1)) if year_m else datetime.now(timezone.utc).year
            try:
                dt = datetime(year, month_num, day, tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                pass

    return None


def _trim_quoted_tail(lines: list[str]) -> list[str]:
    """Remove the forwarded-quote block that Outlook appends at the bottom.

    Detects 'Στάλθηκε από Outlook...' or a bare 'From: ...' line that
    starts the re-quoted history and drops everything from there onwards.
    """
    for i, line in enumerate(lines):
        if _RE_SENT_FROM.match(line) or _RE_FROM_QUOTE.match(line):
            return lines[:i]
    return lines


def parse_pdf_file(path: str) -> dict:
    """Extract text from a PDF and return an email-like payload dict.

    Keys returned:
        subject      – first non-empty line before the embedded email headers,
                       or the filename stem if the PDF has no readable text
        body         – actual message body (after email header block, before
                       forwarded-quote tail)
        sender_email – extracted from 'Από:' header block, or None
        sender_name  – extracted from 'Από:' header block, or None
        received_at  – ISO-8601 string parsed from 'Eστάλη:' header, or file mtime
        attachment_paths – empty list
    """
    try:
        from pdfminer.high_level import extract_text
    except ImportError as exc:
        raise ImportError(
            "pdfminer.six is required for PDF import. "
            "Install it with: pip install pdfminer.six"
        ) from exc

    raw: str = extract_text(path) or ""
    text = _normalize_text(raw)

    lines = text.splitlines()

    # ------------------------------------------------------------------
    # Step 1: determine subject from the preamble (lines before "Από:")
    # ------------------------------------------------------------------
    preamble_lines = []
    for line in lines:
        if _RE_FROM.match(line):
            break
        preamble_lines.append(line)

    non_empty_preamble = [ln.strip() for ln in preamble_lines if ln.strip()]
    subject = non_empty_preamble[0] if non_empty_preamble else Path(path).stem

    # ------------------------------------------------------------------
    # Step 2: parse embedded email headers (Από / Προς / Eστάλη)
    # ------------------------------------------------------------------
    headers = _parse_email_headers(lines)

    # ------------------------------------------------------------------
    # Step 3: extract body after the header block, drop quoted tail
    # ------------------------------------------------------------------
    body_lines = lines[headers["body_start_index"]:]
    body_lines = _trim_quoted_tail(body_lines)
    body = "\n".join(body_lines).strip()

    # If the PDF has no recognisable header block body_start_index == 0,
    # meaning no email headers were found — use the full text as body.
    if not body:
        body = text.strip()

    # ------------------------------------------------------------------
    # Step 4: received_at — prefer parsed date, fall back to file mtime
    # ------------------------------------------------------------------
    received_at = headers["received_at"]

    # If the Eστάλη: line had no year the parsed date defaults to the
    # current year, which may be wrong.  Try to find a complete numeric
    # date (dd/mm/yyyy) anywhere in the preamble as a higher-confidence
    # source and use it to override.
    preamble_text = " ".join(preamble_lines)
    m_num = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", preamble_text)
    if m_num:
        try:
            d, mo, y = int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3))
            received_at = datetime(y, mo, d, tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass

    if not received_at:
        try:
            mtime = os.path.getmtime(path)
            received_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            received_at = None

    return {
        "subject": subject,
        "body": body,
        "sender_email": headers["sender_email"],
        "sender_name": headers["sender_name"],
        "received_at": received_at,
        "attachment_paths": [],
    }
