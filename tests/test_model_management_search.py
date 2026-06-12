import sqlite3

from model_management import (
    ELEM_BREAKER_MT,
    ELEM_BREAKER_YT,
    _element_type_filter_options,
    get_model_management_statistics,
    search_elements,
)
from strings_proxy import STRINGS as S


class _DummyApp:
    def __init__(self, conn):
        self.conn = conn
        self.ELEMENT_TYPES = [
            ELEM_BREAKER_MT,
            ELEM_BREAKER_YT,
            "Μετασχηματιστής 150/20KV",
            "Transformer",
        ]


def _setup_db():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE substations (
            id INTEGER PRIMARY KEY,
            name TEXT,
            base_distance_km REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            element_model_id INTEGER,
            element_type TEXT,
            name TEXT,
            serial_number TEXT,
            maintenance_date TEXT,
            manufacturer TEXT,
            installation_space TEXT,
            operating_status TEXT,
            maintenance_cycle TEXT,
            breaker_category TEXT,
            manufacture_year TEXT,
            is_main_switch INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE element_models (
            id INTEGER PRIMARY KEY,
            element_category TEXT,
            model_name TEXT,
            manufacturer TEXT
        )
        """
    )
    cur.executemany(
        "INSERT INTO element_models (id, element_category, model_name, manufacturer) VALUES (?, ?, ?, ?)",
        [
            (1, ELEM_BREAKER_MT, "MV-100", "ABB"),
            (2, ELEM_BREAKER_MT, "MV-200", "ABB"),
            (3, ELEM_BREAKER_YT, "HV-100", "Siemens"),
            (4, "Μετασχηματιστής 150/20KV", "TR-100", "GE"),
        ],
    )
    cur.executemany(
        "INSERT INTO substations (id, name, base_distance_km) VALUES (?, ?, ?)",
        [
            (1, "NEAR SUB", 20.0),
            (2, "MID SUB", 120.0),
            (3, "FAR SUB", 260.0),
        ],
    )
    cur.executemany(
        """
        INSERT INTO elements (
            id, substation_id, element_model_id, element_type, name, serial_number, maintenance_date,
            manufacturer, installation_space, operating_status, maintenance_cycle,
            breaker_category, manufacture_year, is_main_switch
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                1,
                1,
                ELEM_BREAKER_MT,
                "MV OIL OLD",
                "SN1",
                "2024-01-01",
                "ABB",
                "OUT",
                "Ενεργή",
                "6",
                "Ελαίου",
                "2000",
                0,
            ),
            (
                2,
                2,
                2,
                ELEM_BREAKER_MT,
                "MV SF6 CENTRAL",
                "SN2",
                "2024-01-01",
                "ABB",
                "OUT",
                "Ενεργή",
                "6",
                "SF6",
                "2015",
                1,
            ),
            (
                3,
                3,
                3,
                ELEM_BREAKER_YT,
                "HV SF6",
                "SN3",
                "2024-01-01",
                "Siemens",
                "OUT",
                "Ενεργή",
                "6",
                "SF6",
                "2010",
                0,
            ),
            (
                4,
                3,
                4,
                "Μετασχηματιστής 150/20KV",
                "TR 1",
                "SN4",
                "2024-01-01",
                "GE",
                "OUT",
                "Ενεργή",
                "6",
                "",
                "1999",
                0,
            ),
            (
                5,
                1,
                1,
                ELEM_BREAKER_MT,
                "MV VACUUM",
                "SN5",
                "2024-01-01",
                "ABB",
                "OUT",
                "Ανενεργή",
                "6",
                "Κενού",
                "2018",
                2,
            ),
        ],
    )
    conn.commit()
    return conn


def test_search_elements_filters_old_oil_mv_breakers():
    conn = _setup_db()
    app = _DummyApp(conn)

    rows = search_elements(
        app,
        element_type_filter=ELEM_BREAKER_MT,
        breaker_category_filter="Ελαίου",
        year_relation=S["MESSAGES"].get("OLDER_THAN_YEAR_LABEL", "Παλαιότερα από"),
        reference_year=2006,
    )

    assert [row[2] for row in rows] == ["MV OIL OLD"]


def test_search_elements_filters_central_sf6_breakers_across_hv_and_mv():
    conn = _setup_db()
    app = _DummyApp(conn)

    rows = search_elements(
        app,
        element_type_filter=S["MESSAGES"].get(
            "ALL_BREAKERS_OPTION", "Όλοι οι Διακόπτες"
        ),
        breaker_category_filter="SF6",
        breaker_role_filter=S["MESSAGES"].get("BREAKER_LABEL_CENTRAL", "Κεντρικός"),
    )

    assert [row[2] for row in rows] == ["HV SF6", "MV SF6 CENTRAL"]


def test_search_elements_sorts_by_distance_and_applies_distance_limit():
    conn = _setup_db()
    app = _DummyApp(conn)

    rows = search_elements(app, sort_direction="distance_desc")
    assert rows[0][11] == "FAR SUB"
    assert rows[-1][11] == "NEAR SUB"

    near_rows = search_elements(
        app, distance_limit_km=50, sort_direction="distance_desc"
    )
    assert {row[11] for row in near_rows} == {"NEAR SUB"}


def test_search_elements_applies_greater_than_distance_limit():
    conn = _setup_db()
    app = _DummyApp(conn)

    rows = search_elements(
        app,
        distance_relation=S["MESSAGES"].get(
            "DISTANCE_GREATER_THAN_LABEL", "Μεγαλύτερη από"
        ),
        distance_limit_km=100,
        sort_direction="distance_desc",
    )

    assert {row[11] for row in rows} == {"MID SUB", "FAR SUB"}


def test_search_elements_hides_inactive_by_default():
    conn = _setup_db()
    app = _DummyApp(conn)

    rows = search_elements(
        app,
        element_type_filter=ELEM_BREAKER_MT,
    )

    assert {row[2] for row in rows} == {"MV OIL OLD", "MV SF6 CENTRAL"}

    rows_with_inactive = search_elements(
        app,
        element_type_filter=ELEM_BREAKER_MT,
        include_inactive=True,
    )
    assert {row[2] for row in rows_with_inactive} == {
        "MV OIL OLD",
        "MV SF6 CENTRAL",
        "MV VACUUM",
    }


def test_element_type_filter_options_normalize_transformer_aliases():
    conn = _setup_db()
    app = _DummyApp(conn)

    options = _element_type_filter_options(app, conn)

    assert options.count("Μετασχηματιστής 150/20KV") == 1
    assert "Transformer" not in options


def test_model_management_statistics_collects_expected_graph_data():
    conn = _setup_db()
    app = _DummyApp(conn)

    stats = get_model_management_statistics(app)

    assert stats["rows_count"] == 4
    assert stats["pies"]["types_hv_breakers"] == [("SF6", 1)]
    assert stats["pies"]["types_mv_breakers"] == [("SF6", 1), ("Ελαίου", 1)]
    assert stats["pies"]["age_transformers"] == [("21-30", 1)]
    assert stats["bars"]["manufacturer_count_models"] == {
        ELEM_BREAKER_MT: [("ABB", 2)],
        ELEM_BREAKER_YT: [("Siemens", 1)],
        "Μετασχηματιστής 150/20KV": [("GE", 1)],
    }
    assert stats["bars"]["most_used_models_per_category"][ELEM_BREAKER_MT] == [
        ("MV-100", 1),
        ("MV-200", 1),
    ]


def test_model_management_statistics_respects_distance_and_inactive_filters():
    conn = _setup_db()
    app = _DummyApp(conn)

    far_stats = get_model_management_statistics(
        app,
        distance_relation=S["MESSAGES"].get(
            "DISTANCE_GREATER_THAN_LABEL", "Μεγαλύτερη από"
        ),
        distance_limit_km=100,
    )
    assert far_stats["rows_count"] == 3
    assert far_stats["pies"]["types_mv_breakers"] == [("SF6", 1)]

    inactive_stats = get_model_management_statistics(app, include_inactive=True)
    assert inactive_stats["rows_count"] == 5
    assert inactive_stats["pies"]["types_mv_breakers"] == [
        ("SF6", 1),
        ("Ελαίου", 1),
        ("Κενού", 1),
    ]
