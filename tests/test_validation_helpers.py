import pytest

from validation import (
    is_interconnection_gate,
    validate_breaker_category_required,
    validate_gate_assignment,
)
from strings_proxy import STRINGS as S

ELEM_BREAKER_YT = S["MESSAGES"].get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = S["MESSAGES"].get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")


def test_is_interconnection_gate():
    assert is_interconnection_gate("ΠΥΛΗ 1-2") is True
    assert is_interconnection_gate("ΠΥΛΗ 1") is False
    assert is_interconnection_gate("") is False


def test_validate_gate_assignment_valid():
    # regular gate allowed for any element type
    assert validate_gate_assignment(ELEM_BREAKER_MT, "Κεντρικός", "ΠΥΛΗ 1")
    # interconnection allowed only for MV interconnection breaker
    assert validate_gate_assignment(ELEM_BREAKER_MT, "Διασυνδετικός", "ΠΥΛΗ 1-2")


def test_validate_gate_assignment_invalid():
    with pytest.raises(ValueError):
        validate_gate_assignment(ELEM_BREAKER_YT, "Κεντρικός", "ΠΥΛΗ 1-2")
    with pytest.raises(ValueError):
        validate_gate_assignment(ELEM_BREAKER_MT, "Κεντρικός", "ΠΥΛΗ 1-2")


def test_validate_breaker_category_required():
    # valid when provided
    assert validate_breaker_category_required(ELEM_BREAKER_MT, "SF6")
    # invalid when missing
    with pytest.raises(ValueError):
        validate_breaker_category_required(ELEM_BREAKER_MT, "")
    # non-breaker types are ignored
    assert validate_breaker_category_required("Μετασχηματιστής 150/20KV", None)
