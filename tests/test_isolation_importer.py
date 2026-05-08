from datetime import datetime
import sqlite3

from email_eml_parser import parse_eml_file
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
        "Την απομόνωση του Μ/Σ Νο3 του Υ/Σ Εορδαίας, "
        "την Δευτέρα 30/03/2026 και ώρα 08:00, "
        "Την επανάζευξη του Μ/Σ Νο3 του Υ/Σ Εορδαίας, "
        "την Κυριακή 05/04/2026 και ώρα 14:00"
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


def test_match_element_ids_from_text_prefers_exact_transformer_designator_over_variants():
    matched_ids, matched_phrases = match_element_ids_from_text(
        "Απομόνωση των Μ/Σ Νο2 και Μ/Σ Νο1 του Υ/Σ ΙΑΣΜΟΥ",
        [
            (486, "ΜΣ1", "101136", "Μετασχηματιστής 150/20KV", "ΠΥΛΗ 1"),
            (487, "ΜΣ2", "113600", "Μετασχηματιστής 150/20KV", "ΠΥΛΗ 2"),
            (
                488,
                "ΜΣ2 (ΛΑΘΟΣ ΤΥΠΟΣ)",
                "113600",
                "Μετασχηματιστής 150/20KV",
                "ΠΥΛΗ 2",
            ),
            (
                489,
                "ΜΣ2 (ΠΑΛΙΟΣ)",
                "90881",
                "Μετασχηματιστής 150/20KV",
                "ΠΥΛΗ 2",
            ),
        ],
    )

    assert matched_ids == [486, 487]
    assert matched_phrases[486] == ["ΜΣ1"]
    assert matched_phrases[487] == ["ΜΣ2"]


def test_match_element_ids_from_text_matches_r_breaker_without_hyphen():
    matched_ids, _matched_phrases = match_element_ids_from_text(
        "σκοπός της απομόνωσης είναι ο έλεγχος του Ρ235 για Ιονισμό",
        [
            (822, "Ρ-235", "LMO30125", "Διακόπτης ΡΙ", "ΠΥΛΗ 3"),
            (859, "Ρ-435", "LM0301224", "Διακόπτης ΡΙ", "ΠΥΛΗ 4"),
        ],
    )

    assert 822 in matched_ids


def test_parse_isolation_request_text_handles_holiday_and_same_day_range():
    current_year = datetime.now().year
    text = (
        "Καλημέρα σε όλους. Επισυνάπτω αίτηση άδειας εργασίας για την απομόνωση "
        "του Μ/Σ Νο2 του Υ/Σ ΛΗΤΗΣ για σήμερα Μ. ΠΕΜΠΤΗ 9/4 και ώρα 10:00 έως 14:00."
    )

    parsed = parse_isolation_request_text(text)

    assert parsed["substation_candidates"] == ["ΛΗΤΗΣ"]
    assert parsed["start_datetime"] == f"{current_year}-04-09 10:00"
    assert parsed["end_datetime"] == f"{current_year}-04-09 14:00"


def test_parse_isolation_request_text_handles_weekday_range_and_substation():
    current_year = datetime.now().year
    text = (
        "Επισυνάπτω αίτηση άδειας εργασίας για την Απομόνωση των Μ/Σ Νο3 και ΖΥΓΩΝ Νο3 "
        "του Υ/Σ ΣΤΑΓΕΙΡΩΝ την ΠΑΡΑΣΚΕΥΗ 17/4 και ώρα 09.00 μέχρι 14.00"
    )

    parsed = parse_isolation_request_text(text)

    assert parsed["substation_candidates"] == ["ΣΤΑΓΕΙΡΩΝ"]
    assert parsed["start_datetime"] == f"{current_year}-04-17 09:00"
    assert parsed["end_datetime"] == f"{current_year}-04-17 14:00"


def test_match_substation_handles_candidate_with_trailing_schedule_words():
    class AppStub:
        def _find_substation_in_text(self, _text, _substations):
            return None

    matched = match_substation(
        AppStub(),
        "του Υ/Σ ΛΗΤΗΣ για σήμερα Μ. ΠΕΜΠΤΗ 9/4 και ώρα 10:00 έως 14:00",
        [(77, "ΛΗΤΗ")],
    )

    assert matched == (77, "ΛΗΤΗ")


def test_match_substation_handles_declension_difference_with_db_name():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (15, "ΣΤΑΓΕΙΡΑ"))

    class AppStub:
        def __init__(self, conn):
            self.conn = conn

        def _find_substation_in_text(self, _text, _substations):
            return None

    matched = match_substation(
        AppStub(conn),
        "του Υ/Σ ΣΤΑΓΕΙΡΩΝ την ΠΑΡΑΣΚΕΥΗ 17/4 και ώρα 09.00 μέχρι 14.00",
        [(15, "ΣΤΑΓΕΙΡΑ")],
    )

    assert matched == (15, "ΣΤΑΓΕΙΡΑ")


def test_match_substation_handles_tuple_rows_from_shared_matcher():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute(
        "INSERT INTO substations (id, name) VALUES (?, ?)",
        (21, "ΣΤΑΓΕΙΡΑ"),
    )

    class AppStub:
        def __init__(self, conn):
            self.conn = conn

        def _find_substation_in_text(self, _text, _substations):
            return None

    matched = match_substation(
        AppStub(conn),
        "του Υ/Σ ΣΤΑΓΕΙΡΩΝ την ΠΑΡΑΣΚΕΥΗ 17/4 και ώρα 09.00 μέχρι 14.00",
        [(21, "ΣΤΑΓΕΙΡΑ")],
    )

    assert matched == (21, "ΣΤΑΓΕΙΡΑ")


def test_match_substation_from_recovered_html_eml_body(tmp_path):
    html_body = (
        "<html><head>"
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
        "</head><body>"
        "<p>Καλημέρα σας.</p>"
        "<p>Επισυνάπτω αίτηση άδειας εργασίας για την απομόνωση του Μ/Σ Νο2 "
        "του Υ/Σ ΛΗΤΗΣ για 11/5 και ώρα 09.00 έως 13.00.</p>"
        "</body></html>"
    )
    raw_eml = (
        b"Subject: Isolation request\r\n"
        b"From: Sender <sender@example.com>\r\n"
        b"To: Receiver <receiver@example.com>\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"Content-Transfer-Encoding: 8bit\r\n\r\n" + html_body.encode("cp1253")
    )
    eml_path = tmp_path / "isolation_html.eml"
    eml_path.write_bytes(raw_eml)

    parsed = parse_eml_file(str(eml_path))

    assert "<html" not in parsed["body"].lower()
    assert "ΛΗΤΗΣ" in parsed["body"]

    class AppStub:
        def _find_substation_in_text(self, _text, _substations):
            return None

    matched = match_substation(
        AppStub(),
        parsed["body"],
        [(77, "ΛΗΤΗ")],
    )

    assert matched == (77, "ΛΗΤΗ")
