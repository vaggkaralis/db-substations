"""Small validation helpers for gate and breaker assignment logic.

Exports:
- is_interconnection_gate(gate_value)
- validate_gate_assignment(element_type, breaker_type, gate_value)
- validate_breaker_category_required(element_type, breaker_category_value)
"""

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
        if element_type != "Διακόπτης ΜΤ":
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
    if element_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"] and (
        breaker_category_value is None or str(breaker_category_value).strip() == ""
    ):
        raise ValueError("Η κατηγορία διακόπτη είναι υποχρεωτική για τους διακόπτες!")
    return True
