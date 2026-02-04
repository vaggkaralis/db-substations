"""
Parse .eml files and return normalized email fields.
"""
import re
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime


_QUOTE_BREAK_PATTERNS = [
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE),
    re.compile(r"^\s*-{2,}\s*Forwarded message\s*-{2,}\s*$", re.IGNORECASE),
    re.compile(r"^\s*From:\s", re.IGNORECASE),
    re.compile(r"^\s*Sent:\s", re.IGNORECASE),
    re.compile(r"^\s*To:\s", re.IGNORECASE),
    re.compile(r"^\s*Subject:\s", re.IGNORECASE),
    re.compile(r"^\s*On .+ wrote:\s*$", re.IGNORECASE),
    re.compile(r"^\s*Από:\s", re.IGNORECASE),
    re.compile(r"^\s*Στάλθηκε:\s", re.IGNORECASE),
    re.compile(r"^\s*Προς:\s", re.IGNORECASE),
    re.compile(r"^\s*Θέμα:\s", re.IGNORECASE),
]


def _trim_first_message(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    trimmed = []
    for line in lines:
        if line.strip().startswith(">"):
            break
        if any(pat.search(line) for pat in _QUOTE_BREAK_PATTERNS):
            break
        trimmed.append(line)

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

    cleaned = _clean_body(content or "")
    return _trim_first_message(cleaned)


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

    return {
        "subject": subject,
        "body": body,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "received_at": received_at,
    }
