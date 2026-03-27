from datetime import datetime

from email_text_utils import iter_substation_name_candidates
from isolation_importer import (
    match_element_ids_from_text,
    match_substation,
    parse_isolation_request_text,
)


def test_iter_substation_name_candidates_includes_base_name():
    candidates = iter_substation_name_candidates("ΕΟΡΔΑΙΑ (ΠΤΟΛΕΜΑΪΔΑ II)")

    assert "ΕΟΡΔΑΙΑ (ΠΤΟΛΕΜΑΪΔΑ II)" in candidates
    assert "ΕΟΡΔΑΙΑ" in candidates
    assert "ΠΤΟΛΕΜΑΪΔΑ II" in candidates


def test_parse_isolation_request_text_extracts_two_datetimes():
    text = (
        "Την απομόνωση του Μ/Σ Νο3 του Υ/Σ Εορδαίας, την Δευτέρα 30/03/2026 και ώρα 08:00, "
        "Την επανάζευξη του Μ/Σ Νο3 του Υ/Σ Εορδαίας, την Κυριακή 05/04/2026 και ώρα 14:00"
    )

    parsed = parse_isolation_request_text(text)

    assert parsed["start_datetime"] == "2026-03-30 08:00"
    assert parsed["end_datetime"] == "2026-04-05 14:00"


def test_parse_isolation_request_text_handles_same_day_range_without_year():
    current_year = datetime.now().year
    text = "Υ/Σ ΜΠΟΤΣΑΡΗ, για την ΔΕΥΤΕΡΑ 23/3 και ώρα 09.00 έως 14.00"

    parsed = parse_isolation_request_text(text)

    assert parsed["start_datetime"] == f"{current_year}-03-23 09:00"
    assert parsed["end_datetime"] == f"{current_year}-03-23 14:00"


def test_match_substation_matches_base_name_from_parenthetical_entry():
    class AppStub:
        def _find_substation_in_text(self, _text, _substations):
            return None

    matched = match_substation(
        AppStub(),
        "παρουσία επιτηρητή στον Υ/Σ Εορδαίας για απομόνωση",
        [(19, "ΕΟΡΔΑΙΑ (ΠΤΟΛΕΜΑΪΔΑ II)")],
    )

    assert matched == (19, "ΕΟΡΔΑΙΑ (ΠΤΟΛΕΜΑΪΔΑ II)")


def test_match_element_ids_from_text_matches_transformer_designator():
    matched_ids, matched_phrases = match_element_ids_from_text(
        "Την απομόνωση του Μ/Σ Νο3 του Υ/Σ Εορδαίας",
        [(346, "ΜΣ3", "98292/77", "Μετασχηματιστής 150/20KV", "ΠΥΛΗ 3")],
    )

    assert matched_ids == [346]
    assert matched_phrases[346] == ["ΜΣ3"]


def test_match_element_ids_from_text_matches_r_breaker_without_hyphen():
    matched_ids, _matched_phrases = match_element_ids_from_text(
        "σκοπός της απομόνωσης είναι ο έλεγχος του Ρ235 για Ιονισμό",
        [
            (822, "Ρ-235", "LMO30125", "Διακόπτης ΡΙ", "ΠΥΛΗ 3"),
            (859, "Ρ-435", "LM0301224", "Διακόπτης ΡΙ", "ΠΥΛΗ 4"),
        ],
    )

    assert 822 in matched_ids
