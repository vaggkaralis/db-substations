import re
from datetime import datetime

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
    r"(?P<date>\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?).{0,40}?ώρα\s*(?P<start_time>\d{1,2}[:.]\d{2})\s*(?:έως|εως|ως|to|-|–)\s*(?P<end_time>\d{1,2}[:.]\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_SUBSTATION_PATTERN = re.compile(
    r"Υ/Σ\s+([A-ΩA-Za-zΆΈΉΊΌΎΏΪΫάέήίόύώϊϋΐΰ0-9()./\-\s]+?)(?=(?:,|\.|\n|\s+την\s+|\s+προκειμένου|\s+για\s+χειρισμ))",
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


def _clean_whitespace(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_time_value(value: str) -> str:
    return re.sub(r"\s+", "", value or "").replace(".", ":")


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


def extract_date_times(text: str) -> list[str]:
    matches = []
    occupied_spans = []

    for match in _DATE_RANGE_PATTERN.finditer(text or ""):
        start_value = _parse_datetime(match.group("date"), match.group("start_time"))
        end_value = _parse_datetime(match.group("date"), match.group("end_time"))
        if start_value and start_value not in matches:
            matches.append(start_value)
        if end_value and end_value not in matches:
            matches.append(end_value)
        occupied_spans.append(match.span())

    for match in _DATE_TIME_PATTERN.finditer(text or ""):
        span = match.span()
        if any(
            not (span[1] <= used_start or span[0] >= used_end)
            for used_start, used_end in occupied_spans
        ):
            continue
        parsed = _parse_datetime(match.group("date"), match.group("time"))
        if parsed and parsed not in matches:
            matches.append(parsed)
    return matches


def extract_substation_candidates(text: str) -> list[str]:
    candidates = []
    for match in _SUBSTATION_PATTERN.finditer(text or ""):
        candidate = re.sub(r"\s+", " ", match.group(1) or "").strip(" .,")
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
    for candidate in parsed.get("substation_candidates", []):
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

    matched_ids = []
    matched_phrases = {}
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
            matched_ids.append(element_id)
            matched_phrases[element_id] = list(dict.fromkeys(supporting))

    return matched_ids, matched_phrases
