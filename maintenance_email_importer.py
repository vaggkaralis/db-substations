"""
Shared utilities to import maintenance records from email metadata.
"""

import re
import sqlite3
from datetime import datetime

from database import init_db
from email_text_utils import normalize_text as _normalize_text
from email_text_utils import tokenize_text as _tokenize_text
from email_text_utils import tokens_match as _tokens_match
from email_text_utils import normalize_substation_tokens as _normalize_substation_tokens
from email_text_utils import tokenize_substation_text as _tokenize_substation_text
from email_text_utils import iter_substation_name_candidates as _iter_substation_name_candidates
from onedrive_hybrid_storage import ensure_maintenance_folders
from settings import DB_PATH as DEFAULT_DB_PATH

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
        "κυτ φιλλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
        "φιλιππων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
        "φιλλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
        "φιλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
        "φιλλιπων": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
        "κυτ φιλιππων μσ1": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
        "κυτ φιλλιπων μσ1": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "κυυτ θεσσαλονικης": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",
    "κυτ θεσσαλονικησ": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",
    "κυυτ θεσσαλονικησ": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",  # with final sigma and double upsilon
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
    c.execute("SELECT id, name FROM people WHERE active=1")
    people = c.fetchall()

    tokens = _tokenize_text(body_text)
    token_set = set(tokens)
    compact = re.sub(r"[^0-9a-zα-ω]+", "", _normalize_text(body_text))

    found = set()
    for pid, name in people:
        if pid in exclude_ids:
            continue
        person_tokens = _tokenize_text(name)
        if not person_tokens:
            continue
        
        # Database stores "SURNAME FIRSTNAME", so check both tokens
        first_token = person_tokens[0]  # Surname
        last_token = person_tokens[-1]   # First name
        
        # Check if surname (first token) appears in body - with Greek declension matching
        if first_token:
            # Exact match
            if first_token in token_set:
                found.add(pid)
                continue
            # Check for Greek declension variants (e.g., ιορδανιδη vs ιορδανιδησ)
            for body_token in token_set:
                if _tokens_match([body_token], [first_token]):
                    found.add(pid)
                    break
            if pid in found:
                continue
        
        # Check if first name (last token) appears in body
        if last_token and last_token in token_set:
            found.add(pid)
            continue
        
        # Check initial + surname pattern
        initial = first_token[0] if first_token else ""
        if initial and first_token and f"{initial}{first_token}" in compact:
            found.add(pid)

    return found

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
    normalized_body = re.sub(r"(μσ|ms)\s*[ilι]\b", r"\g<1>1", normalized_body)
    compact_body = re.sub(r"[^0-9a-zα-ω]+", "", normalized_body)
    compact_body = re.sub(r"(μσ|ms)[ilι](?![0-9])", r"\g<1>1", compact_body)
    has_satyf = "σατυφ" in compact_body
    transformer_numbers = set(
        re.findall(r"(?:μσ|μετασχηματιστησ)[^0-9]{0,3}([0-9]+)", normalized_body)
    )
    transformer_numbers.update(
        re.findall(r"(?:ms|transformer)[^0-9]{0,3}([0-9]+)", normalized_body)
    )
    ms_numbers = set(re.findall(r"μσ([0-9]+)", compact_body))
    ms_numbers.update(re.findall(r"ms([0-9]+)", compact_body))

    matched = set()
    motor_drive_candidates = []
    for elem_id, elem_name, elem_type in elements:
        base = _normalize_text(elem_name)
        compact = re.sub(r"[^0-9a-zα-ω]+", "", base)
        variants = {compact}

        digits = "".join(ch for ch in compact if ch.isdigit())
        if digits:
            if "μετασχηματιστης" in _normalize_text(elem_type) or compact.startswith(
                "μσ"
            ):
                variants.add(f"μσ{digits}")
                variants.add(f"μετασχηματιστης{digits}")
            if compact.startswith("ρ"):
                variants.add(f"ρ{digits}")

        element_ms_numbers = set(
            re.findall(r"(?:μσ|μετασχηματιστησ)[^0-9]{0,3}([0-9]+)", base)
        )
        element_ms_numbers.update(
            re.findall(r"(?:ms|transformer)[^0-9]{0,3}([0-9]+)", base)
        )
        element_ms_numbers.update(re.findall(r"μσ([0-9]+)", compact))
        element_ms_numbers.update(re.findall(r"ms([0-9]+)", compact))

        elem_type_norm = _normalize_text(elem_type)
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

    return matched


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
        formatted_body = _format_email_body_for_readability(body)

        fields = ["substation_id", "date_time", "overall_comments"]
        values = [substation["id"], date_time_value, formatted_body]

        if "maintenance_type" in maint_cols:
            fields.append("maintenance_type")
            values.append("Email")

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
            conn, body, exclude_ids={responsible_id} if responsible_id else set()
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

        element_ids = _find_elements_in_body(conn, body, substation["id"])
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
        maintenance_name = maint_row[0] if maint_row and isinstance(maint_row, (tuple, list)) else (maint_row["name"] if maint_row else f"maintenance_{maintenance_id}")

        c.execute("SELECT maintenance_type FROM maintenance WHERE id=?", (maintenance_id,))
        type_row = c.fetchone()
        maintenance_type = type_row[0] if type_row and isinstance(type_row, (tuple, list)) else (type_row["maintenance_type"] if type_row else "Email")

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

        conn.commit()

        return True, maintenance_id
    finally:
        if close_conn:
            conn.close()
