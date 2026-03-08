"""
Parse .eml files and return normalized email fields.
"""

import re
import tempfile
from pathlib import Path
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime

_SEPARATOR_PATTERNS = [
    re.compile(r"^\s*_{10,}\s*$"),  # Outlook-style separator line
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE),
    re.compile(r"^\s*-{2,}\s*Forwarded message\s*-{2,}\s*$", re.IGNORECASE),
]

_HEADER_PATTERNS = [
    re.compile(r"^\s*From:\s", re.IGNORECASE),
    re.compile(r"^\s*Sent:\s", re.IGNORECASE),
    re.compile(r"^\s*Date:\s", re.IGNORECASE),  # Added Date pattern
    re.compile(r"^\s*To:\s", re.IGNORECASE),
    re.compile(r"^\s*Subject:\s", re.IGNORECASE),
    re.compile(r"^\s*Cc:\s", re.IGNORECASE),
    re.compile(r"^\s*Bcc:\s", re.IGNORECASE),
    re.compile(r"^\s*On .+ wrote:\s*$", re.IGNORECASE),
    re.compile(r"^\s*Από:\s", re.IGNORECASE),
    re.compile(r"^\s*Στάλθηκε:\s", re.IGNORECASE),
    re.compile(r"^\s*Προς:\s", re.IGNORECASE),
    re.compile(r"^\s*Θέμα:\s", re.IGNORECASE),
    re.compile(r"^\s*Cc:\s", re.IGNORECASE),  # Greek Cc
]

_QUOTE_BREAK_PATTERNS = _SEPARATOR_PATTERNS + _HEADER_PATTERNS

_MEDIA_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".webp",
    ".heic",
    ".heif",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".wmv",
    ".m4v",
}


def _trim_first_message(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    trimmed = []
    skip_headers = False  # Flag to skip forwarded/original message headers
    content_started = False
    
    def _is_header_line(value: str) -> bool:
        return any(pat.search(value) for pat in _HEADER_PATTERNS)
    
    for line in lines:
        stripped = line.strip()
        
        # Check if this is a separator for forwarded/original message
        is_separator = any(pat.search(line) for pat in _SEPARATOR_PATTERNS)
        
        if is_separator:
            skip_headers = True
            continue

        # Some PST/plain-text bodies start directly with a mail header block
        # (From/Sent/To/Subject/Cc) without a forwarded separator line.
        # Skip that initial header block until the first blank line.
        if not content_started and _is_header_line(line):
            skip_headers = True
            continue
        
        # If we're in header skip mode, skip until we find the header/body boundary (blank line)
        if skip_headers:
            # Blank line = end of email headers, start of body
            if not stripped:
                skip_headers = False
                continue
            # Keep skipping this line (it's part of the headers)
            continue
        
        # Stop at quote markers
        if stripped.startswith(">"):
            break
        
        trimmed.append(line)
        if stripped:
            content_started = True

    result = "\n".join(trimmed).strip()
    return result or text.strip()


def _clean_body(text: str) -> str:
    if not text:
        return ""

    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if "safelinks.protection.outlook.com" in stripped:
            continue
        if stripped.lower().startswith("sent from outlook"):
            continue
        if stripped.lower().startswith("στάλθηκε από outlook"):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"<\s*https?://[^>]+>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_body(message):
    try:
        body_part = message.get_body(preferencelist=("plain", "html"))
    except Exception:
        body_part = None

    if body_part is None:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    body_part = part
                    break
            if body_part is None:
                for part in message.walk():
                    if part.get_content_type() == "text/html":
                        body_part = part
                        break
        else:
            body_part = message

    if body_part is None:
        return ""

    try:
        content = body_part.get_content()
    except Exception:
        try:
            content = body_part.get_payload(decode=True).decode(errors="ignore")
        except Exception:
            content = ""

    if body_part.get_content_type() == "text/html":
        content = re.sub(r"<[^>]+>", " ", content)
        content = re.sub(r"\s+", " ", content).strip()

    # Trim BEFORE cleaning to preserve line breaks needed for pattern matching
    trimmed = _trim_first_message(content or "")
    return _clean_body(trimmed)


def _extract_media_attachment_paths(message):
    paths = []
    temp_dir = Path(tempfile.mkdtemp(prefix="eml_media_"))
    counter = 1

    try:
        parts = list(message.iter_attachments())
    except Exception:
        parts = []

    for part in parts:
        filename = (part.get_filename() or "").strip()
        if not filename:
            ext_guess = ""
            ctype = (part.get_content_type() or "").lower()
            if ctype.startswith("image/"):
                ext_guess = ".jpg"
            elif ctype.startswith("video/"):
                ext_guess = ".mp4"
            filename = f"attachment_{counter}{ext_guess}"

        safe_name = re.sub(r"[\\/:*?\"<>|]", "_", filename)
        ext = Path(safe_name).suffix.lower()
        ctype = (part.get_content_type() or "").lower()
        is_media_type = ctype.startswith("image/") or ctype.startswith("video/")
        if ext not in _MEDIA_EXTENSIONS and not is_media_type:
            counter += 1
            continue

        try:
            payload = part.get_payload(decode=True)
        except Exception:
            payload = None
        if not payload:
            counter += 1
            continue

        dest = temp_dir / safe_name
        idx = 1
        while dest.exists():
            dest = temp_dir / f"{dest.stem}_{idx}{dest.suffix}"
            idx += 1

        try:
            dest.write_bytes(payload)
            paths.append(str(dest))
        except Exception:
            pass

        counter += 1

    return paths


def parse_eml_file(path: str):
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    subject = (msg.get("subject") or "").strip()
    sender_raw = (msg.get("from") or "").strip()
    sender_name, sender_email = parseaddr(sender_raw)

    received_at = ""
    date_header = msg.get("date")
    if date_header:
        try:
            received_at = parsedate_to_datetime(date_header).isoformat()
        except Exception:
            received_at = ""

    body = _extract_body(msg)
    attachment_paths = _extract_media_attachment_paths(msg)

    return {
        "subject": subject,
        "body": body,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "received_at": received_at,
        "attachment_paths": attachment_paths,
    }
