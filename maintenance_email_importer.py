"""
Shared utilities to import maintenance records from email metadata.
"""

import re
import sqlite3
from datetime import datetime

from database import init_db
from import_diagnostics import log_import_diagnostic
from email_eml_parser import sanitize_email_body_for_import
from email_text_utils import normalize_text as _normalize_text
from email_text_utils import tokenize_text as _tokenize_text
from email_text_utils import tokens_match as _tokens_match
from email_text_utils import tokenize_substation_text as _tokenize_substation_text
from email_text_utils import (
    iter_substation_name_candidates as _iter_substation_name_candidates,
)
from onedrive_hybrid_storage import ensure_maintenance_folders
from settings import DB_PATH as DEFAULT_DB_PATH

try:
    from strings_proxy import STRINGS as S
except Exception:
    S = {"MESSAGES": {}}


_FAULT_SUBJECT_STEMS = (
    "βλαβ",  # βλάβη / βλαβη / βλαβών
    "επισκευ",  # επισκευή / επισκευη / επισκευές
    "αποκαταστ",  # αποκατάσταση
    "δυσλειτουργ",  # δυσλειτουργία
    "βραχυκυκλ",  # βραχυκύκλωμα
    "αστοχι",  # αστοχία
    "fault",
    "failure",
    "repair",
    "restore",
    "outage",
)


def infer_maintenance_type_from_subject(
    subject: str, default_type: str | None = None
) -> str:
    """Infer maintenance type from subject keywords.

    If the subject contains fault/repair stems, return a fault label
    (prefer localized configured labels). Otherwise return `default_type`
    (or configured MAINT_TYPE_DEFAULT fallback).
    """
    fallback_default = default_type or S.get("MESSAGES", {}).get(
        "MAINT_TYPE_DEFAULT", "Επαναληπτική συντήρηση"
    )
    text = (subject or "").strip()
    if not text:
        return fallback_default

    text = re.sub(r"^\s*(?:fwd|fw|re)\s*:\s*", "", text, flags=re.IGNORECASE)
    normalized = _normalize_for_alias_lookup(text)
    if not normalized:
        return fallback_default

    has_fault_stem = any(stem in normalized for stem in _FAULT_SUBJECT_STEMS)
    if not has_fault_stem:
        return fallback_default

    maint_types = list(S.get("MESSAGES", {}).get("MAINTENANCE_TYPES", []))
    for candidate in ("Βλάβη", "Fault"):
        if candidate in maint_types:
            return candidate
    return "Βλάβη"


# Map common substation name variations to database names
_SUBSTATION_ALIASES = {
    # Π.ΜΕΛΛΑΣ
    "παυλου μελα": "Π.ΜΕΛΛΑΣ (ΘΕΣΣΑΛ. ΧΙ)",
    "παυλου μελλα": "Π.ΜΕΛΛΑΣ (ΘΕΣΣΑΛ. ΧΙ)",
    "π μελα": "Π.ΜΕΛΛΑΣ (ΘΕΣΣΑΛ. ΧΙ)",
    "π μελλα": "Π.ΜΕΛΛΑΣ (ΘΕΣΣΑΛ. ΧΙ)",
    "π μελλασ": "Π.ΜΕΛΛΑΣ (ΘΕΣΣΑΛ. ΧΙ)",
    # Ν. ΕΛΒΕΤΙΑ
    "νεας ελβετιας": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",
    "νεασ ελβετιασ": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",  # with final sigma
    "νεα ελβετια": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",
    "ν ελβετια": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",
    "ν ελβετιας": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",
    "ν ελβετιασ": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",  # with final sigma
    "νε ελβετιας": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",
    "νε ελβετιασ": "Ν. ΕΛΒΕΤΙΑ (ΘΕΣΣΑΛΟΝΙΚΗ IV)",
    # Μ.ΜΠΟΤΣΑΡΗ
    "μποτσαρη": "Μ.ΜΠΟΤΣΑΡΗ (ΘΕΣΣΑΛΟΝΙΚΗ VIII)",
    "μ μποτσαρη": "Μ.ΜΠΟΤΣΑΡΗ (ΘΕΣΣΑΛΟΝΙΚΗ VIII)",
    # ΠΟΛΙΧΝΗ
    "πολιχνη": "ΠΟΛΙΧΝΗ (ΘΕΣΣΑΛΟΝΙΚΗ IX)",
    "πολιχνης": "ΠΟΛΙΧΝΗ (ΘΕΣΣΑΛΟΝΙΚΗ IX)",
    "υσ πολιχνης": "ΠΟΛΙΧΝΗ (ΘΕΣΣΑΛΟΝΙΚΗ IX)",
    "υ/σ πολιχνης": "ΠΟΛΙΧΝΗ (ΘΕΣΣΑΛΟΝΙΚΗ IX)",
    # ΣΤΑΓΕΙΡΑ
    "σταγειρα": "ΣΤΑΓΕΙΡΑ",
    "σταγειρων": "ΣΤΑΓΕΙΡΑ",
    "υσ σταγειρων": "ΣΤΑΓΕΙΡΑ",
    "υ/σ σταγειρων": "ΣΤΑΓΕΙΡΑ",
    # ΔΟΞΑ
    "δοξα": "ΔΟΞΑ (ΘΕΣΣΑΛΟΝΙΚΗ I)",
    "δοξας": "ΔΟΞΑ (ΘΕΣΣΑΛΟΝΙΚΗ I)",
    "υσ δοξας": "ΔΟΞΑ (ΘΕΣΣΑΛΟΝΙΚΗ I)",
    "υ/σ δοξας": "ΔΟΞΑ (ΘΕΣΣΑΛΟΝΙΚΗ I)",
    # ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ
    "κυτ θεσσαλονικης": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",
    # ΚΥΤ ΦΙΛΙΠΠΩΝ
    "κυτ φιλιππων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "κυτ φιλλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "κυτ φιλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "φιλιππων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "φιλλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "φιλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "κυτ φιλιππων μσ1": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "κυτ φιλλιπων μσ1": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "κυυτ θεσσαλονικης": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",
    "κυτ θεσσαλονικησ": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",
    "κυυτ θεσσαλονικησ": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",
    # ΣΕΡΡΕΣ
    "σερρες": "ΣΕΡΡΕΣ",
    "σερρων": "ΣΕΡΡΕΣ",
    "υσ σερρων": "ΣΕΡΡΕΣ",
    "υ/σ σερρων": "ΣΕΡΡΕΣ",
    # ΜΟΥΔΑΝΙΑ
    "μουδανια": "ΜΟΥΔΑΝΙΑ",
    "μουδανιας": "ΜΟΥΔΑΝΙΑ",
    "μουδανιων": "ΜΟΥΔΑΝΙΑ",
    "υσ μουδανιων": "ΜΟΥΔΑΝΙΑ",
    "υ/σ μουδανιων": "ΜΟΥΔΑΝΙΑ",
    # ΣΕΡΒΙΑ
    "σερβια": "ΣΕΡΒΙΑ",
    "σερβιας": "ΣΕΡΒΙΑ",
    "σερβιων": "ΣΕΡΒΙΑ",
    "υσ σερβιων": "ΣΕΡΒΙΑ",
    "υ/σ σερβιων": "ΣΕΡΒΙΑ",
    # ΣΚΟΤΙΝΑ (περιοχή ΠΛΑΤΑΜΩΝΑ)
    "σκοτινα": "ΠΛΑΤΑΜΩΝΑΣ",
    "σκοτινας": "ΠΛΑΤΑΜΩΝΑΣ",
    "μσ2 σκοτινα": "ΠΛΑΤΑΜΩΝΑΣ",
    "σκοτινα μσ2": "ΠΛΑΤΑΜΩΝΑΣ",
    "υς σκοτινα": "ΠΛΑΤΑΜΩΝΑΣ",
    "υ/σ σκοτινα": "ΠΛΑΤΑΜΩΝΑΣ",
    # ΓΙΑΝΝΙΤΣΑ (Ν.ΠΕΛΛΑ) - also known as Πέλλας
    "πελλα": "ΓΙΑΝΝΙΤΣΑ (Ν.ΠΕΛΛΑ)",
    "πελλας": "ΓΙΑΝΝΙΤΣΑ (Ν.ΠΕΛΛΑ)",
    "γιαννιτσα": "ΓΙΑΝΝΙΤΣΑ (Ν.ΠΕΛΛΑ)",
    "γιαννιτσης": "ΓΙΑΝΝΙΤΣΑ (Ν.ΠΕΛΛΑ)",
    "υσ πελλας": "ΓΙΑΝΝΙΤΣΑ (Ν.ΠΕΛΛΑ)",
    "υ/σ πελλας": "ΓΙΑΝΝΙΤΣΑ (Ν.ΠΕΛΛΑ)",
    # ΣΧΟΛΑΡΙ
    "σχολαριου": "ΣΧΟΛΑΡΙ (ΘΕΣΣΑΛΟΝΙΚΗ VI)",
    "υσ σχολαριου": "ΣΧΟΛΑΡΙ (ΘΕΣΣΑΛΟΝΙΚΗ VI)",
    "υ σ σχολαριου": "ΣΧΟΛΑΡΙ (ΘΕΣΣΑΛΟΝΙΚΗ VI)",
    "υσ σχολαρι": "ΣΧΟΛΑΡΙ (ΘΕΣΣΑΛΟΝΙΚΗ VI)",
    "υ σ σχολαρι": "ΣΧΟΛΑΡΙ (ΘΕΣΣΑΛΟΝΙΚΗ VI)",
    # ΜΑΓΙΚΟ ΞΑΝΘΗΣ
    "μαγικου": "ΜΑΓΙΚΟ ΞΑΝΘΗΣ",
    "υσ μαγικου": "ΜΑΓΙΚΟ ΞΑΝΘΗΣ",
    "υ σ μαγικου": "ΜΑΓΙΚΟ ΞΑΝΘΗΣ",
}


def _normalize_for_alias_lookup(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"[^0-9a-zα-ω]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _lookup_substation_by_name(conn, substation_name: str):
    """Helper to query database for a substation by exact name."""
    c = conn.cursor()
    c.execute("SELECT id, name FROM substations WHERE name = ?", (substation_name,))
    row = c.fetchone()
    if row:
        return dict(row)

    # Fallback: normalized lookup (handles punctuation/spacing variations)
    wanted = _normalize_for_alias_lookup(substation_name)
    if not wanted:
        return None

    c.execute("SELECT id, name FROM substations")
    for db_row in c.fetchall():
        db_name_norm = _normalize_for_alias_lookup(db_row["name"])
        if db_name_norm == wanted:
            return dict(db_row)

    return None


def _get_table_columns(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def _format_email_body_for_readability(body: str) -> str:
    """Format imported email body for better readability in the UI."""
    if not body:
        return ""

    text = body.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Ensure common mail headers begin on their own line.
    header_patterns = [
        r"From:",
        r"Sent:",
        r"Date:",
        r"To:",
        r"Cc:",
        r"Bcc:",
        r"Subject:",
        r"Από:",
        r"Στάλθηκε:",
        r"Προς:",
        r"Θέμα:",
    ]
    for pattern in header_patterns:
        text = re.sub(rf"\s+({pattern})", r"\n\1", text, flags=re.IGNORECASE)

    # Add stronger visual separation before forwarded-message starts.
    text = re.sub(r"\n(?=(From:|Από:))", "\n\n", text, flags=re.IGNORECASE)

    # Outlook / Gmail forwarded separators and quote markers.
    text = re.sub(
        r"\s+(?=(?:-{2,}\s*Original Message\s*-{2,}|-{2,}\s*Forwarded message\s*-{2,}|On .+ wrote:))",
        "\n\n",
        text,
        flags=re.IGNORECASE,
    )

    # Keep paragraph spacing consistent.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _parse_subject_for_substation_and_date(subject: str):
    if not subject:
        return None, None
    subject = subject.strip()
    subject = re.sub(r"^\s*(?:fwd|fw|re)\s*:\s*", "", subject, flags=re.IGNORECASE)
    date_match = None

    patterns = [
        r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})",
        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, subject)
        if match:
            date_match = match
            break

    date_str = None
    if date_match:
        parts = date_match.groups()
        if len(parts[0]) == 4:
            year, month, day = parts
        else:
            day, month, year = parts
        try:
            date_str = datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            date_str = None

    substation_part = subject
    if date_match:
        substation_part = subject.replace(date_match.group(0), " ")
    substation_part = re.sub(r"[|\-–—:_()\[\]]+", " ", substation_part)
    substation_part = re.sub(r"\s+", " ", substation_part).strip()

    return substation_part or None, date_str


def _match_substation_by_name(conn, subject_substation: str):
    if not subject_substation:
        return None
    normalized_subject = _normalize_for_alias_lookup(subject_substation)
    if not normalized_subject:
        return None

    # Check aliases first
    if normalized_subject in _SUBSTATION_ALIASES:
        alias_target = _SUBSTATION_ALIASES[normalized_subject]
        result = _lookup_substation_by_name(conn, alias_target)
        if result:
            return result

    c = conn.cursor()
    c.execute("SELECT id, name FROM substations")
    rows = c.fetchall()

    best_match = None
    best_score = 0

    for row in rows:
        name = row["name"]
        normalized_name = _normalize_text(name)
        if normalized_name == normalized_subject:
            return dict(row)
        if (
            normalized_subject in normalized_name
            or normalized_name in normalized_subject
        ):
            score = min(len(normalized_name), len(normalized_subject))
            if score > best_score:
                best_score = score
                best_match = dict(row)

    return best_match


def _match_substation_in_text(conn, text: str):
    tokens = _tokenize_substation_text(text)
    if not tokens:
        return None

    # Check if any alias appears in the text - prioritize longer/more specific aliases
    normalized_text = _normalize_for_alias_lookup(text)
    best_alias_match = None
    best_alias_length = 0

    for alias, target_name in _SUBSTATION_ALIASES.items():
        if alias in normalized_text and len(alias) > best_alias_length:
            best_alias_match = target_name
            best_alias_length = len(alias)

    if best_alias_match:
        result = _lookup_substation_by_name(conn, best_alias_match)
        if result:
            return result

    c = conn.cursor()
    c.execute("SELECT id, name FROM substations")
    rows = c.fetchall()

    # Collect all matching substations with their match quality (token count)
    matches = []
    for row in rows:
        for candidate_name in _iter_substation_name_candidates(row["name"]):
            name_tokens = _tokenize_substation_text(candidate_name)
            if not name_tokens:
                continue
            for i in range(len(tokens) - len(name_tokens) + 1):
                candidate = tokens[i : i + len(name_tokens)]
                if _tokens_match(candidate, name_tokens):
                    # Score based on number of tokens matched (more is better)
                    matches.append((len(name_tokens), dict(row)))
                    break  # Found a match for this row, no need to check other positions

    # Return the match with the most tokens (most specific/longer match)
    if matches:
        best = max(matches, key=lambda item: item[0])
        return best[1]

    return None


def _match_person_by_sender(conn, sender_email: str, sender_name: str):
    c = conn.cursor()
    c.execute("SELECT id, name, email FROM people WHERE active=1")
    people = [dict(row) for row in c.fetchall()]

    if sender_email:
        email_lower = sender_email.strip().lower()
        for person in people:
            if person.get("email") and person["email"].strip().lower() == email_lower:
                return person

    sender_tokens = _tokenize_text(sender_name)
    if sender_tokens:
        sender_full = " ".join(sender_tokens)
        for person in people:
            if " ".join(_tokenize_text(person.get("name"))) == sender_full:
                return person
        for person in people:
            person_tokens = _tokenize_text(person.get("name"))
            if person_tokens and person_tokens[-1] in sender_tokens:
                return person

    return None


def _find_people_in_body(conn, body_text: str, exclude_ids=None):
    exclude_ids = exclude_ids or set()
    c = conn.cursor()
    c.execute("SELECT id, name FROM people WHERE active=1 ORDER BY id")
    people = c.fetchall()

    tokens = _tokenize_text(body_text)
    token_pairs = list(zip(tokens, tokens[1:]))
    normalized_body = re.sub(r"[^0-9a-zα-ω]+", " ", _normalize_text(body_text))
    normalized_body = re.sub(r"\s+", " ", normalized_body).strip()

    def _person_token_match(body_token: str, person_token: str) -> bool:
        if not body_token or not person_token:
            return False
        if body_token == person_token:
            return True
        # Allow Greek declension variants that differ only by a suffix character.
        if (
            len(body_token) >= 4
            and len(person_token) >= 4
            and body_token[:-1] == person_token[:-1]
        ):
            return True
        return False

    def _matches_initial_and_surname(given_token: str, surname_token: str) -> bool:
        if not given_token or not surname_token or not normalized_body:
            return False
        initial = given_token[0]
        # Match patterns like "Ν. Γιαννουλας" and "Ν Γιαννουλας".
        pattern = rf"\b{re.escape(initial)}\s*[.-]?\s*{re.escape(surname_token)}\b"
        return re.search(pattern, normalized_body) is not None

    def _matches_surname_in_crew_context(surname_token: str) -> bool:
        if not surname_token or not normalized_body:
            return False
        for m in re.finditer(rf"\b{re.escape(surname_token)}\b", normalized_body):
            start = max(0, m.start() - 120)
            end = min(len(normalized_body), m.end() + 120)
            window = normalized_body[start:end]
            if re.search(r"\b(εργαζομεν|συνεργει|υπερωρι|ομαδα|επικεφαλησ)\w*", window):
                return True
        return False

    found = set()
    matched_name_keys = set()
    surname_to_person_ids = {}
    for pid, name in people:
        if pid in exclude_ids:
            continue
        person_tokens = _tokenize_text(name)
        if not person_tokens:
            continue

        surname_to_person_ids.setdefault(person_tokens[0], []).append(pid)

        surname_token = person_tokens[0]
        given_token = person_tokens[-1]
        matched = False

        # Require stronger evidence: contiguous full-name tokens in either order.
        if len(person_tokens) >= 2:
            for left, right in token_pairs:
                if _person_token_match(left, surname_token) and _person_token_match(
                    right, given_token
                ):
                    matched = True
                    break
                if _person_token_match(left, given_token) and _person_token_match(
                    right, surname_token
                ):
                    matched = True
                    break

            # Also support abbreviated form: initial + surname.
            if not matched and _matches_initial_and_surname(given_token, surname_token):
                matched = True
        else:
            # Single-token names are accepted only on exact token match.
            matched = any(_person_token_match(tok, person_tokens[0]) for tok in tokens)

        if not matched:
            continue

        # Collapse duplicate person rows with the same normalized display name.
        name_key = " ".join(person_tokens)
        if name_key in matched_name_keys:
            continue
        matched_name_keys.add(name_key)
        found.add(pid)

    # Fallback for crew lines that mention only surnames, e.g.
    # "Οι εργαζόμενοι Μπάκανος, Μπέης ...".
    # To avoid false positives, accept only unambiguous surnames and only
    # when they appear near crew-related keywords.
    for surname_token, candidate_ids in surname_to_person_ids.items():
        if len(candidate_ids) != 1:
            continue
        pid = candidate_ids[0]
        if pid in exclude_ids or pid in found:
            continue
        if _matches_surname_in_crew_context(surname_token):
            found.add(pid)

    return found


def _find_elements_in_body(conn, body_text: str, substation_id: int):
    c = conn.cursor()
    c.execute(
        "SELECT id, name, element_type FROM elements WHERE substation_id=?",
        (substation_id,),
    )
    elements = c.fetchall()

    normalized_body = _normalize_text(body_text)
    normalized_body = re.sub(r"μ\s*[\./-]\s*σ", "μσ", normalized_body)
    normalized_body = re.sub(r"m\s*[\./-]\s*s", "ms", normalized_body)
    normalized_body = normalized_body.lower()
    normalized_body = re.sub(r"(μσ|ms)\s*[ilι]\b", r"\g<1>1", normalized_body)
    compact_body = re.sub(r"[^0-9a-zα-ω]+", "", normalized_body)
    compact_body = re.sub(r"(μσ|ms)[ilι](?![0-9])", r"\g<1>1", compact_body)
    exact_designators = set()
    for prefix, digits in re.findall(
        r"\b([a-zα-ω]{1,6})\s*[-/ ]\s*([0-9]{1,6})\b", normalized_body
    ):
        exact_designators.add(f"{prefix}{digits}")
    for prefix, digits in re.findall(
        r"\b([a-zα-ω]{1,6})([0-9]{1,6})\b", normalized_body
    ):
        exact_designators.add(f"{prefix}{digits}")
    breaker_refs = set()
    for digits in re.findall(r"\bρ\s*[-/ ]?\s*([0-9]{1,4})\b", normalized_body):
        breaker_refs.add(digits)
    has_satyf = "σατυφ" in compact_body
    # Only extract numbers from explicit designators (e.g., ΜΣ2, ΜΣ-2, Μετασχηματιστής 2)
    transformer_numbers = set()
    ms_numbers = set()
    # Patterns for explicit transformer designators
    explicit_patterns = [
        r"μ[σς][ -]?([0-9]+)\b",
        r"μετασχηματιστ(ης|ής)[ -]?([0-9]+)\b",
        r"ms[ -]?([0-9]+)\b",
        r"transformer[ -]?([0-9]+)\b",
    ]
    for pat in explicit_patterns:
        for m in re.finditer(pat, normalized_body):
            # For patterns with two groups, the number is always the last group
            if len(m.groups()) == 2:
                num = m.group(2)
            else:
                num = m.group(1)
            transformer_numbers.add(num)
            ms_numbers.add(num)

    matched = set()
    exact_breaker_matches = set()
    motor_drive_candidates = []
    for elem_id, elem_name, elem_type in elements:
        base = _normalize_text(elem_name)
        compact = re.sub(r"[^0-9a-zα-ω]+", "", base)
        variants = {compact}

        digits = "".join(ch for ch in compact if ch.isdigit())
        elem_type_norm = _normalize_text(elem_type)
        is_transformer = (
            "μετασχηματιστης" in elem_type_norm
            or compact.startswith("μσ")
            or compact.startswith("ms")
        )
        is_r_breaker = compact.startswith("ρ") and digits != ""

        if digits:
            if is_transformer:
                variants.add(f"μσ{digits}")
                variants.add(f"μετασχηματιστης{digits}")
            if is_r_breaker:
                variants.add(f"ρ{digits}")

        element_ms_numbers = set(
            re.findall(r"(?:μσ|μετασχηματιστησ)[^0-9]{0,3}([0-9]+)", base)
        )
        element_ms_numbers.update(
            re.findall(r"(?:ms|transformer)[^0-9]{0,3}([0-9]+)", base)
        )
        element_ms_numbers.update(re.findall(r"μσ([0-9]+)", compact))
        element_ms_numbers.update(re.findall(r"ms([0-9]+)", compact))

        is_motor_drive = (
            "motor drive" in elem_type_norm
            or elem_type_norm == "motordrive"
            or "md" in compact
            or "σατυφ" in base
        )

        if is_motor_drive:
            motor_drive_candidates.append(
                (elem_id, element_ms_numbers, compact, elem_type_norm)
            )

        if is_motor_drive and has_satyf:
            if element_ms_numbers and (
                element_ms_numbers & (transformer_numbers | ms_numbers)
            ):
                matched.add(elem_id)
                continue
            if (transformer_numbers or ms_numbers) and (
                not element_ms_numbers
                or element_ms_numbers & (transformer_numbers | ms_numbers)
            ):
                matched.add(elem_id)
                continue
            if digits and (digits in transformer_numbers or digits in ms_numbers):
                matched.add(elem_id)
                continue
            if digits and (
                f"μσ{digits}" in compact_body
                or f"μετασχηματιστησ{digits}" in compact_body
            ):
                matched.add(elem_id)
                continue
            if not digits and len(transformer_numbers | ms_numbers) == 1:
                matched.add(elem_id)
                continue

        # Transformers must be referenced explicitly with a transformer designator
        # like ΜΣ2, ΜΣ-2, Μετασχηματιστής 2. Generic mentions like "δύο ΜΣ" must not resolve to ΜΣ2.
        if is_transformer:
            # Only match if explicit designator (ΜΣ2, ΜΣ-2, Μετασχηματιστής 2) with strong operational context is present
            def _has_strong_transformer_context(ms_digits: str) -> bool:
                # Only match if the designator appears as a whole word (not as part of a count or generic mention)
                # e.g., "ΜΣ2", "ΜΣ-2", "Μετασχηματιστής 2"
                patterns = [
                    rf"μ[σς][ -]?{re.escape(ms_digits)}\b",
                    rf"μετασχηματιστ(ης|ής)[ -]?{re.escape(ms_digits)}\b",
                    rf"ms[ -]?{re.escape(ms_digits)}\b",
                    rf"transformer[ -]?{re.escape(ms_digits)}\b",
                ]
                # Require strong operational context near the designator
                for pat in patterns:
                    strong = re.search(
                        rf"(?:\b(συντηρ|εργασ|μετρησ|επανασυνδε|αφαιρεσ|εγκαταστασ)\w*\b[^\n.,;:()]{{0,30}}\b{pat}|\b{pat}[^\n.,;:()]{{0,30}}\b(συντηρ|εργασ|μετρησ|επανασυνδε|αφαιρεσ|εγκαταστασ)\w*\b)",
                        normalized_body,
                    )
                    if strong:
                        return True
                return False

            # Only match if explicit designator and strong context
            if digits and digits in (transformer_numbers | ms_numbers):
                if _has_strong_transformer_context(digits):
                    matched.add(elem_id)
            continue

        # Breakers named Ρ-15 / Ρ-255 must match exact R-designators from the mail,
        # whether written as Ρ15 or Ρ-15.
        if is_r_breaker:
            if digits and digits in breaker_refs:
                matched.add(elem_id)
                exact_breaker_matches.add(elem_id)
            continue

        # For all other numbered elements, allow only exact compact designator matches.
        if is_transformer:
            # Do not allow fallback substring/variant matching for transformers
            continue
        if digits and compact in exact_designators:
            matched.add(elem_id)
            continue

        # Use regex with word boundary to avoid substring matches
        # e.g., "ρ25" should not match "ρ250"
        for var in variants:
            if not var:
                continue
            # Check if variant ends with a digit; if so, ensure next char is not a digit
            if re.search(r"\d$", var):
                # Use negative lookahead to prevent matching if followed by another digit
                pattern = re.escape(var) + r"(?!\d)"
                if re.search(pattern, compact_body):
                    matched.add(elem_id)
                    break
            else:
                # For non-digit endings, simple substring match is fine
                if var in compact_body:
                    matched.add(elem_id)
                    break

    if has_satyf and (transformer_numbers or ms_numbers):
        md_matched = any(eid in matched for eid, _, _, _ in motor_drive_candidates)
        if not md_matched:
            for (
                elem_id,
                element_ms_numbers,
                compact,
                elem_type_norm,
            ) in motor_drive_candidates:
                if element_ms_numbers & (transformer_numbers | ms_numbers):
                    matched.add(elem_id)
            if (
                not any(eid in matched for eid, _, _, _ in motor_drive_candidates)
                and len(motor_drive_candidates) == 1
            ):
                matched.add(motor_drive_candidates[0][0])

    if has_satyf and not (transformer_numbers or ms_numbers):
        md_matched = any(eid in matched for eid, _, _, _ in motor_drive_candidates)
        if not md_matched and len(motor_drive_candidates) == 1:
            matched.add(motor_drive_candidates[0][0])

    # Filter incidental transformer mentions (e.g. "σύγκριση με παλαιότερες
    # τιμές του ΜΣ2") while keeping operational mentions of worked elements.
    def _is_weak_transformer_context(ms_digits: str) -> bool:
        token_pat = rf"μ[σς]{re.escape(ms_digits)}"

        # Strong evidence only when action verbs are close to the same token.
        strong = re.search(
            rf"(?:\b(συντηρ|εργασ|μετρησ|επανασυνδε|αφαιρεσ|εγκαταστασ)\w*\b[^\n.,;:()]{{0,30}}\b{token_pat}\b|\b{token_pat}\b[^\n.,;:()]{{0,30}}\b(συντηρ|εργασ|μετρησ|επανασυνδε|αφαιρεσ|εγκαταστασ)\w*\b)",
            normalized_body,
        )
        if strong:
            return False

        # Weak evidence: comparison / historical reference around the token.
        weak = re.search(
            rf"(?:\b(συγκρι|παλαιοτερ|γραφημα|χαρακτηριστικ)\w*\b[^\n.,;:()]{{0,40}}\b{token_pat}\b|\b{token_pat}\b[^\n.,;:()]{{0,40}}\b(συγκρι|παλαιοτερ|γραφημα|χαρακτηριστικ)\w*\b|\bτιμ\w*\b[^\n.,;:()]{{0,20}}\bτου\b[^\n.,;:()]{{0,20}}\b{token_pat}\b)",
            normalized_body,
        )
        return weak is not None

    for elem_id, elem_name, _elem_type in elements:
        base = _normalize_text(elem_name).lower()
        compact = re.sub(r"[^0-9a-zα-ω]+", "", base)
        ms_match = re.match(r"^μ[σς]([0-9]+)$", compact)
        if not ms_match:
            continue
        if elem_id in matched and _is_weak_transformer_context(ms_match.group(1)):
            matched.discard(elem_id)

    # Exact breaker designators are the highest-confidence matches in email text.
    # When present, avoid preselecting additional elements from the same mail.
    if exact_breaker_matches:
        return exact_breaker_matches

    return matched


def _fetch_person_names_by_ids(conn, person_ids):
    ids = sorted({pid for pid in person_ids if pid is not None})
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, name FROM people WHERE id IN ({placeholders})",
        ids,
    )
    return {row["id"]: row["name"] for row in cur.fetchall()}


def _get_previous_maintenance_defaults(conn, substation_id: int, date_time_value: str):
    c = conn.cursor()
    c.execute(
        """
        SELECT id, maintenance_type, overall_comments, responsible_id
        FROM maintenance
        WHERE substation_id = ? AND date_time < ?
        ORDER BY date_time DESC
        LIMIT 1
        """,
        (substation_id, date_time_value),
    )
    row = c.fetchone()
    if not row:
        return {}

    maintenance_id, maint_type, comments, responsible_id = row

    c.execute(
        "SELECT person_id, role FROM maintenance_people WHERE maintenance_id=?",
        (maintenance_id,),
    )
    people_rows = c.fetchall()
    crew_ids = {pid for pid, role in people_rows if role == "crew"}
    if not responsible_id:
        for pid, role in people_rows:
            if role == "responsible":
                responsible_id = pid
                break

    c.execute(
        "SELECT element_id FROM maintenance_elements WHERE maintenance_id=?",
        (maintenance_id,),
    )
    element_ids = {row[0] for row in c.fetchall()}

    return {
        "maintenance_type": maint_type,
        "overall_comments": comments,
        "responsible_id": responsible_id,
        "crew_ids": crew_ids,
        "element_ids": element_ids,
    }


def _get_db(db_path: str):
    conn = init_db(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_maintenance_from_email(
    *,
    subject,
    body,
    sender_email,
    sender_name,
    received_at,
    attachment_paths=None,
    db_path=DEFAULT_DB_PATH,
    conn=None,
):
    """
    Insert a maintenance record from email metadata.

    Returns: (success: bool, result: id_or_error_message)
    """
    close_conn = False
    if conn is None:
        conn = _get_db(db_path)
        close_conn = True

    try:
        if not subject:
            return False, "Missing subject"

        substation_name, date_str = _parse_subject_for_substation_and_date(subject)

        substation = None
        if substation_name:
            substation = _match_substation_by_name(conn, substation_name)
        if not substation:
            substation = _match_substation_in_text(conn, subject)
        # Only try body match if no subject match found, to prioritize explicit subject mentions
        if not substation:
            substation = _match_substation_in_text(conn, body)
        if not substation:
            return False, "Substation not found in subject or body"

        sanitized_body = sanitize_email_body_for_import(body or "")

        person = _match_person_by_sender(conn, sender_email, sender_name)
        responsible_id = person["id"] if person else None

        date_time_value = None
        if date_str:
            date_time_value = f"{date_str} 00:00:00"
        if received_at and not date_time_value:
            try:
                parsed_received = datetime.fromisoformat(
                    received_at.replace("Z", "+00:00")
                )
                date_time_value = parsed_received.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                date_time_value = None
        if not date_time_value:
            date_time_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        prev_defaults = {}
        if not responsible_id:
            prev_defaults = _get_previous_maintenance_defaults(
                conn, substation["id"], date_time_value
            )
            responsible_id = prev_defaults.get("responsible_id")

        maint_cols = _get_table_columns(conn, "maintenance")
        formatted_body = _format_email_body_for_readability(sanitized_body)

        fields = ["substation_id", "date_time", "overall_comments"]
        values = [substation["id"], date_time_value, formatted_body]

        if "maintenance_type" in maint_cols:
            fields.append("maintenance_type")
            values.append(
                infer_maintenance_type_from_subject(subject, default_type="Email")
            )

        if "user_name" in maint_cols:
            fields.append("user_name")
            values.append(sender_name or sender_email)

        if "responsible_id" in maint_cols and responsible_id:
            fields.append("responsible_id")
            values.append(responsible_id)

        placeholders = ", ".join(["?"] * len(fields))
        insert_sql = (
            f"INSERT INTO maintenance ({', '.join(fields)}) VALUES ({placeholders})"
        )

        c = conn.cursor()
        # Defensive check: avoid creating duplicate maintenance from repeated emails
        existing_mid = None
        try:
            # match by fingerprint: substation_id, date_time, maintenance_type, user_name
            mtype = None
            if "maintenance_type" in maint_cols:
                mtype = infer_maintenance_type_from_subject(
                    subject, default_type="Email"
                )
            uname = sender_name or sender_email
            if mtype is not None:
                c.execute(
                    "SELECT id FROM maintenance WHERE substation_id=? AND date_time=? AND maintenance_type=? AND user_name=? LIMIT 1",
                    (substation["id"], date_time_value, mtype, uname),
                )
                row = c.fetchone()
                if row:
                    existing_mid = row[0]
            # Fallback: match by substation + date_time
            if existing_mid is None:
                c.execute(
                    "SELECT id FROM maintenance WHERE substation_id=? AND date_time=? LIMIT 1",
                    (substation["id"], date_time_value),
                )
                row = c.fetchone()
                if row:
                    existing_mid = row[0]

        except Exception:
            existing_mid = None

        if existing_mid:
            maintenance_id = existing_mid
        else:
            c.execute(insert_sql, values)
            maintenance_id = c.lastrowid

        if responsible_id:
            try:
                c.execute(
                    """
                    INSERT INTO maintenance_people (maintenance_id, person_id, role)
                    VALUES (?, ?, 'responsible')
                    """,
                    (maintenance_id, responsible_id),
                )
            except Exception:
                pass

        crew_ids = _find_people_in_body(
            conn,
            sanitized_body,
            exclude_ids={responsible_id} if responsible_id else set(),
        )
        people_name_map = _fetch_person_names_by_ids(
            conn, set(crew_ids) | ({responsible_id} if responsible_id else set())
        )
        log_import_diagnostic(
            "email_import_people_detected",
            sender_name=sender_name or "",
            sender_email=sender_email or "",
            subject=subject or "",
            substation_id=(
                substation.get("id") if isinstance(substation, dict) else None
            ),
            substation_name=(
                substation.get("name") if isinstance(substation, dict) else ""
            ),
            maintenance_date_time=date_time_value,
            body_length=len(sanitized_body or ""),
            responsible_id=responsible_id,
            responsible_name=people_name_map.get(responsible_id),
            detected_crew_ids=sorted(crew_ids),
            detected_crew_names=[people_name_map.get(pid) for pid in sorted(crew_ids)],
        )
        # Don't use fallback to previous maintenance crew - only include explicitly mentioned crew
        # This prevents false preselection of crew members from previous work

        for pid in crew_ids:
            try:
                c.execute(
                    "INSERT INTO maintenance_people (maintenance_id, person_id, role) VALUES (?, ?, ?)",
                    (maintenance_id, pid, "crew"),
                )
            except Exception:
                pass

        element_ids = _find_elements_in_body(conn, sanitized_body, substation["id"])
        if not element_ids:
            if not prev_defaults:
                prev_defaults = _get_previous_maintenance_defaults(
                    conn, substation["id"], date_time_value
                )
            element_ids = prev_defaults.get("element_ids") or set()

        for elem_id in element_ids:
            try:
                c.execute(
                    "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
                    (maintenance_id, elem_id, ""),
                )
            except Exception:
                pass

        # Pre-create gate/interconnection folders and copy imported media attachments.
        # Import must fail when folder structure cannot be created.
        c.execute("SELECT name FROM maintenance WHERE id=?", (maintenance_id,))
        maint_row = c.fetchone()
        maintenance_name = (
            maint_row[0]
            if maint_row and isinstance(maint_row, (tuple, list))
            else (maint_row["name"] if maint_row else f"maintenance_{maintenance_id}")
        )

        c.execute(
            "SELECT maintenance_type FROM maintenance WHERE id=?", (maintenance_id,)
        )
        type_row = c.fetchone()
        maintenance_type = (
            type_row[0]
            if type_row and isinstance(type_row, (tuple, list))
            else (type_row["maintenance_type"] if type_row else "Email")
        )

        folder_result = ensure_maintenance_folders(
            conn,
            maintenance_id=maintenance_id,
            substation_id=substation["id"],
            maintenance_name=maintenance_name,
            maintenance_type=maintenance_type or "Email",
            date_time=date_time_value,
            element_ids=element_ids,
            attachment_paths=attachment_paths or [],
            db_path=db_path,
        )
        primary_media_folder = folder_result.get("primary_media_folder")
        if primary_media_folder and "onedrive_media_folder_link" in maint_cols:
            c.execute(
                "UPDATE maintenance SET onedrive_media_folder_link=? WHERE id=?",
                (primary_media_folder, maintenance_id),
            )

        c.execute(
            """
            SELECT role, person_id
            FROM maintenance_people
            WHERE maintenance_id=?
            ORDER BY role, person_id
            """,
            (maintenance_id,),
        )
        persisted_people_rows = c.fetchall()
        persisted_ids = {row["person_id"] for row in persisted_people_rows}
        persisted_name_map = _fetch_person_names_by_ids(conn, persisted_ids)
        log_import_diagnostic(
            "email_import_people_persisted",
            maintenance_id=maintenance_id,
            substation_id=(
                substation.get("id") if isinstance(substation, dict) else None
            ),
            people=[
                {
                    "role": row["role"],
                    "person_id": row["person_id"],
                    "person_name": persisted_name_map.get(row["person_id"]),
                }
                for row in persisted_people_rows
            ],
        )

        conn.commit()

        return True, maintenance_id
    finally:
        if close_conn:
            conn.close()
