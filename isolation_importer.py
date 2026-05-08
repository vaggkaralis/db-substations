import re
from datetime import datetime
from pathlib import Path

from email_text_utils import (
    iter_substation_name_candidates,
    normalize_text,
    tokens_match,
    tokenize_text,
    tokenize_substation_text,
)

_DATE_TIME_PATTERN = re.compile(
    r"(?P<date>\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?).{0,40}?ώρα\s*(?P<time>\d{1,2}[:.]\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_DATE_RANGE_PATTERN = re.compile(
    r"(?P<date>\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?).{0,40}?ώρα\s*(?P<start_time>\d{1,2}[:.]\d{2})\s*(?:έως|εως|μέχρι|μεχρι|ως|to|-|–)\s*(?P<end_time>\d{1,2}[:.]\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_RELATIVE_DATE_RANGE_PATTERN = re.compile(
    r"(?P<date_word>σήμερα|σημερα|αύριο|αυριο|μεθαύριο|μεθαυριο).{0,20}?ώρα\s*(?P<start_time>\d{1,2}[:.]\d{2})\s*(?:έως|εως|μέχρι|μεχρι|ως|to|-|–)\s*(?P<end_time>\d{1,2}[:.]\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_RELATIVE_DATE_TIME_PATTERN = re.compile(
    r"(?P<date_word>σήμερα|σημερα|αύριο|αυριο|μεθαύριο|μεθαυριο).{0,20}?ώρα\s*(?P<time>\d{1,2}[:.]\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_SUBSTATION_PATTERN = re.compile(
    r"Υ/Σ\s+([A-ΩA-Za-zΆΈΉΊΌΎΏΪΫάέήίόύώϊϋΐΰ0-9()./\-\s]+?)(?=(?:,|\.|\n|\s+την\s+|\s+για\s+σήμερα|\s+για\s+σημερα|\s+για\s+αύριο|\s+για\s+αυριο|\s+σήμερα\s+|\s+σημερα\s+|\s+αύριο\s+|\s+αυριο\s+|\s+μεθαύριο\s+|\s+μεθαυριο\s+|\s+προκειμένου|\s+σκοπός|\s+σκοποσ|\s+και\s+ώρα|\s+ωρα\s))",
    re.IGNORECASE,
)
_ELEMENT_PHRASE_PATTERNS = [
    re.compile(r"Μ\s*[/.-]?\s*Σ\s*(?:Νο|No|Νο\.)?\s*\d+", re.IGNORECASE),
    re.compile(r"ΜΣ\s*(?:Νο|No|Νο\.)?\s*\d+", re.IGNORECASE),
    re.compile(r"Α/Ζ\s*[0-9A-Za-zΑ-Ωα-ω/-]+", re.IGNORECASE),
    re.compile(r"Ρ\s*[-/]?\s*\d+(?:\s*[-/]\s*Ρ?\s*\d+)?", re.IGNORECASE),
    re.compile(r"ζυγ(?:ό|ο)?\s*[0-9A-Za-zΑ-Ωα-ω/-]+", re.IGNORECASE),
    re.compile(r"ημιζυγ\w*\s+Ρ\s*[-/]?\s*\d+(?:\s*[-/]\s*Ρ?\s*\d+)?", re.IGNORECASE),
]

_ISOLATION_REQUEST_ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".csv",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".eml",
}

_INLINE_ISOLATION_REQUEST_START_PATTERN = re.compile(
    r"(?=^\s*Την\s+απομόνωση\b)",
    re.IGNORECASE | re.MULTILINE,
)

_INLINE_ISOLATION_REQUEST_END_PATTERN = re.compile(
    r"^\s*(?:Οι\s+λεπτομέρειες|Ευχαριστούμε|Με\s+εκτίμηση|Best\s+regards)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _clean_whitespace(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _dedupe_paths(paths):
    ordered = []
    seen = set()
    for path in paths or []:
        normalized = str(path or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _read_text_attachment(path: str) -> str:
    for encoding in ("utf-8", "cp1253", "iso-8859-7", "latin-1"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except Exception:
            continue
    return ""


def _read_spreadsheet_attachment(path: str) -> str:
    try:
        import pandas as pd
    except Exception:
        return ""

    try:
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    except Exception:
        return ""

    lines = []
    for sheet_df in (sheets or {}).values():
        if sheet_df is None:
            continue
        for row in sheet_df.fillna("").itertuples(index=False):
            parts = [str(value).strip() for value in row if str(value).strip()]
            if parts:
                lines.append(" ".join(parts))
    return "\n".join(lines).strip()


def _read_isolation_request_attachment_text(path: str) -> str:
    normalized_path = str(path or "").strip()
    if not normalized_path:
        return ""

    suffix = Path(normalized_path).suffix.lower()
    if suffix == ".pdf":
        try:
            from pdf_parser import parse_pdf_file

            return str((parse_pdf_file(normalized_path) or {}).get("body") or "")
        except Exception:
            return ""
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return _read_spreadsheet_attachment(normalized_path)
    if suffix in {".txt", ".csv"}:
        return _read_text_attachment(normalized_path)
    if suffix == ".eml":
        try:
            from email_eml_parser import parse_eml_file

            return str((parse_eml_file(normalized_path) or {}).get("body") or "")
        except Exception:
            return ""
    return ""


def _compose_isolation_request_text(attachment_text: str, email_body: str) -> str:
    attachment_body = str(attachment_text or "").strip()
    fallback_body = str(email_body or "").strip()
    if not attachment_body:
        return fallback_body
    if not fallback_body:
        return attachment_body
    if normalize_text(fallback_body) in normalize_text(attachment_body):
        return attachment_body
    return f"{attachment_body}\n\n{fallback_body}".strip()


def _split_inline_isolation_request_bodies(email_body: str) -> list[str]:
    cleaned_body = _clean_whitespace(email_body)
    if not cleaned_body:
        return []

    end_match = _INLINE_ISOLATION_REQUEST_END_PATTERN.search(cleaned_body)
    relevant_body = (
        cleaned_body[: end_match.start()].strip() if end_match else cleaned_body
    )
    starts = [
        match.start()
        for match in _INLINE_ISOLATION_REQUEST_START_PATTERN.finditer(relevant_body)
    ]
    if len(starts) <= 1:
        return []

    request_bodies = []
    for index, start_offset in enumerate(starts):
        end_offset = (
            starts[index + 1] if index + 1 < len(starts) else len(relevant_body)
        )
        chunk = relevant_body[start_offset:end_offset].strip()
        if chunk:
            request_bodies.append(chunk)
    return request_bodies


def split_isolation_email_payload(payload: dict | None) -> list[dict]:
    source_payload = dict(payload or {})
    email_body = source_payload.get("body") or ""
    attachment_paths = _dedupe_paths(
        source_payload.get("document_attachment_paths")
        or source_payload.get("all_attachment_paths")
        or []
    )
    request_paths = [
        path
        for path in attachment_paths
        if Path(path).suffix.lower() in _ISOLATION_REQUEST_ATTACHMENT_EXTENSIONS
    ]
    if not request_paths:
        inline_requests = _split_inline_isolation_request_bodies(email_body)
        if len(inline_requests) > 1:
            split_payloads = []
            total = len(inline_requests)
            for index, request_body in enumerate(inline_requests, start=1):
                split_payload = dict(source_payload)
                split_payload["body"] = request_body
                split_payload.setdefault("all_attachment_paths", attachment_paths)
                split_payload["_isolation_split_key"] = f"email-body:{index}"
                split_payload["_isolation_split_index"] = index
                split_payload["_isolation_split_total"] = total
                split_payload["_isolation_split_label"] = f"Αίτημα {index}"
                split_payloads.append(split_payload)
            return split_payloads

        single_payload = dict(source_payload)
        single_payload.setdefault("all_attachment_paths", attachment_paths)
        single_payload["_isolation_split_key"] = "email-body:1"
        single_payload["_isolation_split_index"] = 1
        single_payload["_isolation_split_total"] = 1
        single_payload["_isolation_split_label"] = ""
        return [single_payload]

    split_payloads = []
    total = len(request_paths)
    for index, request_path in enumerate(request_paths, start=1):
        attachment_text = _read_isolation_request_attachment_text(request_path)
        split_payload = dict(source_payload)
        split_payload["body"] = _compose_isolation_request_text(
            attachment_text,
            email_body,
        )
        split_payload["attachment_paths"] = [request_path]
        split_payload["document_attachment_paths"] = [request_path]
        split_payload["all_attachment_paths"] = [request_path]
        split_payload["_isolation_attachment_text"] = attachment_text
        split_payload["_isolation_split_key"] = (
            f"attachment:{index}:{Path(request_path).name.lower()}"
        )
        split_payload["_isolation_split_index"] = index
        split_payload["_isolation_split_total"] = total
        split_payload["_isolation_split_label"] = Path(request_path).name
        split_payloads.append(split_payload)

    return split_payloads


def _normalize_time_value(value: str) -> str:
    return re.sub(r"\s+", "", value or "").replace(".", ":")


def _resolve_relative_date(
    date_word: str, reference_dt: datetime | None = None
) -> datetime:
    base = reference_dt or datetime.now()
    normalized = normalize_text(date_word or "")
    if normalized == "αυριο":
        return base.replace(hour=0, minute=0, second=0, microsecond=0).fromordinal(
            base.toordinal() + 1
        )
    if normalized == "μεθαυριο":
        return base.replace(hour=0, minute=0, second=0, microsecond=0).fromordinal(
            base.toordinal() + 2
        )
    return base


def _parse_datetime(
    value: str, time_value: str, reference_dt: datetime | None = None
) -> str | None:
    date_parts = [part for part in re.split(r"[./-]", value or "") if part]
    if len(date_parts) not in (2, 3):
        return None

    try:
        day = int(date_parts[0])
        month = int(date_parts[1])
        if len(date_parts) == 3:
            year = int(date_parts[2])
            if year < 100:
                year += 2000
        else:
            year = (reference_dt or datetime.now()).year
        parsed = datetime.strptime(
            f"{day:02d}/{month:02d}/{year:04d} {_normalize_time_value(time_value)}",
            "%d/%m/%Y %H:%M",
        )
        return parsed.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def _parse_relative_datetime(
    date_word: str, time_value: str, reference_dt: datetime | None = None
) -> str | None:
    try:
        base = _resolve_relative_date(date_word, reference_dt)
        parsed = datetime.strptime(
            f"{base.strftime('%d/%m/%Y')} {_normalize_time_value(time_value)}",
            "%d/%m/%Y %H:%M",
        )
        return parsed.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def _append_match(matches: list[str], value: str | None):
    if value and value not in matches:
        matches.append(value)


def extract_date_times(text: str) -> list[str]:
    matches = []
    occupied_spans = []

    for match in _DATE_RANGE_PATTERN.finditer(text or ""):
        start_value = _parse_datetime(match.group("date"), match.group("start_time"))
        end_value = _parse_datetime(match.group("date"), match.group("end_time"))
        _append_match(matches, start_value)
        _append_match(matches, end_value)
        occupied_spans.append(match.span())

    for match in _RELATIVE_DATE_RANGE_PATTERN.finditer(text or ""):
        span = match.span()
        if any(
            not (span[1] <= used_start or span[0] >= used_end)
            for used_start, used_end in occupied_spans
        ):
            continue
        start_value = _parse_relative_datetime(
            match.group("date_word"), match.group("start_time")
        )
        end_value = _parse_relative_datetime(
            match.group("date_word"), match.group("end_time")
        )
        _append_match(matches, start_value)
        _append_match(matches, end_value)
        occupied_spans.append(match.span())

    for match in _DATE_TIME_PATTERN.finditer(text or ""):
        span = match.span()
        if any(
            not (span[1] <= used_start or span[0] >= used_end)
            for used_start, used_end in occupied_spans
        ):
            continue
        parsed = _parse_datetime(match.group("date"), match.group("time"))
        _append_match(matches, parsed)

    for match in _RELATIVE_DATE_TIME_PATTERN.finditer(text or ""):
        span = match.span()
        if any(
            not (span[1] <= used_start or span[0] >= used_end)
            for used_start, used_end in occupied_spans
        ):
            continue
        parsed = _parse_relative_datetime(match.group("date_word"), match.group("time"))
        _append_match(matches, parsed)
    return matches


def extract_substation_candidates(text: str) -> list[str]:
    candidates = []
    for match in _SUBSTATION_PATTERN.finditer(text or ""):
        candidate = re.sub(r"\s+", " ", match.group(1) or "").strip(" .,")
        candidate = re.sub(
            r"\s+(?:για|την|σήμερα|σημερα|αύριο|αυριο|μεθαύριο|μεθαυριο|σκοπός|σκοποσ|και|ώρα|ωρα)\b.*$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip(" .,")
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def extract_element_phrases(text: str) -> list[str]:
    phrases = []
    for pattern in _ELEMENT_PHRASE_PATTERNS:
        for match in pattern.finditer(text or ""):
            phrase = re.sub(r"\s+", " ", match.group(0) or "").strip()
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return phrases


def parse_isolation_request_text(text: str) -> dict:
    cleaned = _clean_whitespace(text)
    date_times = extract_date_times(cleaned)
    start_datetime = date_times[0] if len(date_times) >= 1 else None
    end_datetime = date_times[1] if len(date_times) >= 2 else None
    substation_candidates = extract_substation_candidates(cleaned)
    element_phrases = extract_element_phrases(cleaned)
    return {
        "raw_text": cleaned,
        "notes": cleaned,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "substation_candidates": substation_candidates,
        "element_phrases": element_phrases,
    }


def _tokens_contained(container_tokens, candidate_tokens) -> bool:
    if not container_tokens or not candidate_tokens:
        return False
    return all(token in container_tokens for token in candidate_tokens)


def match_substation(app, text: str, substations) -> tuple[int, str] | None:
    parsed = parse_isolation_request_text(text)

    try:
        from maintenance_email_importer import _match_substation_in_text
    except Exception:
        _match_substation_in_text = None

    for candidate in parsed.get("substation_candidates", []):
        if _match_substation_in_text and getattr(app, "conn", None):
            shared_match = _match_substation_in_text(app.conn, candidate)
            if shared_match:
                return (shared_match["id"], shared_match["name"])

        if getattr(app, "_find_substation_in_text", None):
            match = app._find_substation_in_text(candidate, substations)
            if match:
                return match

        candidate_tokens = tokenize_substation_text(candidate)
        for substation_id, substation_name in substations:
            for candidate_name in iter_substation_name_candidates(substation_name):
                name_tokens = tokenize_substation_text(candidate_name)
                if _tokens_contained(name_tokens, candidate_tokens):
                    return (substation_id, substation_name)

    text_tokens = tokenize_substation_text(text)
    if text_tokens:
        for substation_id, substation_name in substations:
            for candidate_name in iter_substation_name_candidates(substation_name):
                name_tokens = tokenize_substation_text(candidate_name)
                if not name_tokens:
                    continue
                for idx in range(len(text_tokens) - len(name_tokens) + 1):
                    if tokens_match(
                        text_tokens[idx : idx + len(name_tokens)], name_tokens
                    ):
                        return (substation_id, substation_name)

    if getattr(app, "_find_substation_in_text", None):
        match = app._find_substation_in_text(text, substations)
        if match:
            return match

    if _match_substation_in_text and getattr(app, "conn", None):
        shared_match = _match_substation_in_text(app.conn, text)
        if shared_match:
            return (shared_match["id"], shared_match["name"])

    return None


def match_element_ids_from_text(
    text: str, element_rows
) -> tuple[list[int], dict[int, list[str]]]:
    normalized_text = normalize_text(text or "")
    normalized_text = re.sub(r"μ\s*[/.-]?\s*σ", "μσ", normalized_text)
    compact_text = re.sub(r"[^0-9a-zα-ω]+", "", normalized_text)
    text_tokens = set(tokenize_text(text or ""))
    phrases = extract_element_phrases(text or "")
    phrase_tokens = {phrase: set(tokenize_text(phrase)) for phrase in phrases}
    exact_designators = set()
    breaker_numbers = set()
    transformer_numbers = set()

    for prefix, digits in re.findall(
        r"\b([a-zα-ω]{1,6})\s*[-/ ]\s*([0-9]{1,6})\b", normalized_text
    ):
        exact_designators.add(f"{prefix}{digits}")
    for prefix, digits in re.findall(
        r"\b([a-zα-ω]{1,6})([0-9]{1,6})\b", normalized_text
    ):
        exact_designators.add(f"{prefix}{digits}")
    for digits in re.findall(r"\bρ\s*[-/ ]?\s*(\d{1,4})\b", normalized_text):
        breaker_numbers.add(digits)
    for digits in re.findall(
        r"(?:μσ|μετασχηματιστ(?:ης|ησ)?|ms|transformer)\s*(?:νο|no|νο\.)?\s*[-/ ]?\s*(\d+)\b",
        normalized_text,
    ):
        transformer_numbers.add(digits)
    exact_transformer_designators = {
        designator
        for designator in exact_designators
        if re.fullmatch(r"(?:μσ|ms)\d+", designator)
    }

    matched_entries = []
    for row in element_rows or []:
        if len(row) < 3:
            continue
        element_id = row[0]
        name = str(row[1] or "")
        serial_number = str(row[2] or "")
        element_type = str(row[3] or "") if len(row) > 3 else ""
        normalized_name = normalize_text(name)
        compact_name = re.sub(r"[^0-9a-zα-ω]+", "", normalized_name)
        name_tokens = set(tokenize_text(name))
        digits = "".join(ch for ch in compact_name if ch.isdigit())
        element_type_norm = normalize_text(element_type)
        is_transformer = (
            "μετασχηματιστ" in element_type_norm
            or compact_name.startswith(("μσ", "ms"))
        )
        is_r_breaker = compact_name.startswith("ρ") and bool(digits)
        matched = False
        supporting = []

        if is_transformer and digits and digits in transformer_numbers:
            matched = True
            supporting.append(name)

        if not matched and is_r_breaker and digits in breaker_numbers:
            matched = True
            supporting.append(name)

        if not matched and compact_name and compact_name in exact_designators:
            matched = True
            supporting.append(name)

        if not matched and normalized_name and normalized_name in normalized_text:
            matched = True
            supporting.append(name)

        if not matched and serial_number:
            normalized_serial = normalize_text(serial_number)
            compact_serial = re.sub(r"[^0-9a-zα-ω]+", "", normalized_serial)
            if compact_serial and compact_serial in compact_text:
                matched = True
                supporting.append(serial_number)

        if not matched and name_tokens and _tokens_contained(text_tokens, name_tokens):
            matched = True
            supporting.append(name)

        if not matched:
            for phrase, tokens in phrase_tokens.items():
                if tokens and (
                    _tokens_contained(name_tokens, tokens)
                    or _tokens_contained(tokens, name_tokens)
                ):
                    matched = True
                    supporting.append(phrase)

        if matched:
            matched_entries.append(
                {
                    "element_id": element_id,
                    "supporting": list(dict.fromkeys(supporting)),
                    "is_transformer": is_transformer,
                    "digits": digits,
                    "compact_name": compact_name,
                    "normalized_name": normalized_name,
                    "name": name,
                }
            )

    selected_entries = []
    best_transformer_entries = {}
    for entry in matched_entries:
        transformer_key = None
        if entry["is_transformer"] and entry["digits"] in transformer_numbers:
            transformer_key = entry["digits"]

        if not transformer_key:
            selected_entries.append(entry)
            continue

        score = (
            1 if entry["compact_name"] in exact_transformer_designators else 0,
            1 if entry["compact_name"] in exact_designators else 0,
            1 if "(" not in entry["name"] else 0,
            -len(entry["normalized_name"]),
        )
        current = best_transformer_entries.get(transformer_key)
        if current is None or score > current[0]:
            best_transformer_entries[transformer_key] = (score, entry)

    selected_entries.extend(
        entry for _score, entry in best_transformer_entries.values()
    )
    selected_entries.sort(key=lambda entry: entry["element_id"])

    matched_ids = [entry["element_id"] for entry in selected_entries]
    matched_phrases = {
        entry["element_id"]: entry["supporting"] for entry in selected_entries
    }

    return matched_ids, matched_phrases
