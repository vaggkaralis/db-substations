"""Small validation helpers for gate and breaker assignment logic.

Exports:
- is_interconnection_gate(gate_value)
- validate_gate_assignment(element_type, breaker_type, gate_value)
- validate_breaker_category_required(element_type, breaker_category_value)
"""

from strings_proxy import STRINGS as S

# Canonical breaker element names from strings
ELEM_BREAKER_YT = S["MESSAGES"].get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = S["MESSAGES"].get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")
ELEMENT_BREAKER_SUBSTR = S["MESSAGES"].get("ELEMENT_BREAKER_SUBSTR", "Διακόπτης")


def is_interconnection_gate(gate_value):
    try:
        return bool(gate_value and "-" in str(gate_value))
    except Exception:
        return False


def validate_gate_assignment(element_type, breaker_type, gate_value):
    """Validate that a gate assignment is allowed for the given element/breaker type.

    Raises ValueError with a user-friendly message when invalid.
    Returns True when valid.
    """
    if not gate_value:
        return True
    if is_interconnection_gate(gate_value):
        # Interconnection gates are only allowed for MV interconnection breakers
        if element_type != ELEM_BREAKER_MT:
            raise ValueError(
                "Οι πύλες σύνδεσης (π.χ. ΠΥΛΗ 1-2) επιτρέπονται μόνο για Διακόπτης ΜΤ τύπου 'Διασυνδετικός'."
            )
        if breaker_type != "Διασυνδετικός":
            raise ValueError(
                "Οι πύλες σύνδεσης (π.χ. ΠΥΛΗ 1-2) επιτρέπονται μόνο σε διασυνδετικούς διακόπτες (Τύπος: Διασυνδετικός)."
            )
    return True


def validate_breaker_category_required(element_type, breaker_category_value):
    """Ensure breaker category is provided for circuit breakers; raise ValueError if missing."""
    if element_type in [ELEM_BREAKER_YT, ELEM_BREAKER_MT] and (
        breaker_category_value is None or str(breaker_category_value).strip() == ""
    ):
        raise ValueError("Η κατηγορία διακόπτη είναι υποχρεωτική για τους διακόπτες!")
    return True


def filter_people_for_maintenance(people_rows, responsible_person_id=None):
    """Return (responsible_people, crew_people) filtered for maintenance.

    people_rows: iterable of (id, name, role)
    If responsible_person_id is provided but the person isn't in allowed responsible
    roles, they are prepended to the responsible_people list so they remain selectable.
    """
    people = list(people_rows)
    # Use canonical role matching to be tolerant to diacritics/variants in DB
    responsible_people = [
        p for p in people if canonical_role(p[2]) in ALLOWED_RESPONSIBLE_ROLES
    ]
    crew_people = [p for p in people if canonical_role(p[2]) != "Υποστήριξη"]

    # If a preselected responsible person isn't in the allowed list, prepend them so they remain selectable
    if responsible_person_id and not any(
        p[0] == responsible_person_id for p in responsible_people
    ):
        found = next((p for p in people if p[0] == responsible_person_id), None)
        if found:
            responsible_people.insert(0, found)

    return responsible_people, crew_people


# Central list of allowed roles (locked enum) in preferred display order
# Ordered according to user preference: high-priority first
PEOPLE_ROLES = [
    "Τομεάρχης ΤΕΙ",
    "Υποτομεάρχης ΤΕΙ",
    "Ειδικό Στέλεχος Γ'",
    "Μηχανικός",
    "Εργοδηγός",
    "Αρχιτεχνίτης",
    "Τεχνίτης",
    "Χειριστής",
    "Υποστήριξη",
]


# Role categories mapping (single source of truth)
ROLE_CATEGORIES = {
    "Μηχανικοί": {
        "Τομεάρχης ΤΕΙ",
        "Υποτομεάρχης ΤΕΙ",
        "Ειδικό Στέλεχος Γ'",
        "Μηχανικός",
    },
    "Τεχνικοί": {"Εργοδηγός", "Αρχιτεχνίτης", "Τεχνίτης", "Χειριστής"},
    "Λοιπά": {"Υποστήριξη"},
}

ALLOWED_RESPONSIBLE_ROLES = ROLE_CATEGORIES["Μηχανικοί"]


def categorize_role(role_value):
    """Return the category name for a given role string.

    If role_value doesn't match any known roles, returns 'Λοιπά'.
    """
    if not role_value:
        return "Λοιπά"

    import unicodedata

    def _norm(s):
        s = (s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        # remove diacritics
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        # replace punctuation with spaces, keep alphanumerics and whitespace
        s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
        # collapse whitespace
        parts = [p for p in s.split() if p]
        return " ".join(parts)

    rv = _norm(role_value)
    for cat, roles in ROLE_CATEGORIES.items():
        for r in roles:
            if _norm(r) == rv or _norm(r) in rv or rv in _norm(r):
                return cat
    # catch common variants/transliterations for engineering roles
    if "υποτο" in rv or "υποτομε" in rv or "ypoto" in rv:
        return "Μηχανικοί"
    if "ειδ" in rv or "ειδικ" in rv or "eidik" in rv:
        return "Μηχανικοί"
    return "Λοιπά"


def group_people_by_category(people_rows):
    """Group people rows into a dict keyed by category.

    people_rows: iterable of (id, name, role, ...)
    Returns Ordered dict-like mapping: {category: [rows...]}. Categories appear in order: Μηχανικοί, Τεχνικοί, Λοιπά.
    """
    from collections import OrderedDict

    result = OrderedDict()
    for cat in ["Μηχανικοί", "Τεχνικοί", "Λοιπά"]:
        result[cat] = []

    for row in people_rows:
        # assume role is at index 2
        role = row[2] if len(row) > 2 else None
        cat = categorize_role(role)
        result.setdefault(cat, []).append(row)

    return result


def canonical_role(role_value):
    """Return the canonical role name from PEOPLE_ROLES matching the provided role_value.

    Matching prefers exact normalized equality, then normalized substring matches, in the
    order of `PEOPLE_ROLES` so priorities are preserved.
    Returns None if no match found.
    """
    if not role_value:
        return None
    import unicodedata

    def _norm(s):
        s = (s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
        parts = [p for p in s.split() if p]
        return " ".join(parts)

    rv = _norm(role_value)

    # First pass: exact normalized equality
    for pr in PEOPLE_ROLES:
        if _norm(pr) == rv:
            return pr

    # Second pass: normalized whole-word match (prefer earlier PEOPLE_ROLES)
    import re

    for pr in PEOPLE_ROLES:
        prn = _norm(pr)
        if re.search(r"\b" + re.escape(prn) + r"\b", rv) or re.search(
            r"\b" + re.escape(rv) + r"\b", prn
        ):
            return pr

    # Try simple transliteration fallbacks (common ascii variants like TEI, G)
    rv_alt = rv.replace("tei", "τει")
    for pr in PEOPLE_ROLES:
        prn = _norm(pr)
        if re.search(r"\b" + re.escape(prn) + r"\b", rv_alt) or re.search(
            r"\b" + re.escape(rv_alt) + r"\b", prn
        ):
            return pr

    rv_alt2 = rv.replace("g", "γ")
    for pr in PEOPLE_ROLES:
        prn = _norm(pr)
        if re.search(r"\b" + re.escape(prn) + r"\b", rv_alt2) or re.search(
            r"\b" + re.escape(rv_alt2) + r"\b", prn
        ):
            return pr

    rv_alt3 = rv.replace("tei", "τει").replace("g", "γ")
    for pr in PEOPLE_ROLES:
        prn = _norm(pr)
        if re.search(r"\b" + re.escape(prn) + r"\b", rv_alt3) or re.search(
            r"\b" + re.escape(rv_alt3) + r"\b", prn
        ):
            return pr

    return None


def is_user_responsible_capable(role: str) -> bool:
    """Check if a user role can be assigned as maintenance responsible.

    Args:
        role: The role name to check

    Returns:
        True if the role can be assigned as maintenance responsible
    """
    return role in ALLOWED_RESPONSIBLE_ROLES
