from database import init_db
from DBrun import SubstationApp
from strings_proxy import STRINGS as S

# canonical breaker names for tests
ELEM_BREAKER_YT = S["MESSAGES"].get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = S["MESSAGES"].get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")


def setup_app_with_substation_and_transformers(transformer_names):
    conn = init_db(":memory:")
    c = conn.cursor()
    # create a substation
    c.execute("INSERT INTO substations (name) VALUES (?)", ("TEST",))
    sid = c.lastrowid
    # add transformers
    for name in transformer_names:
        c.execute(
            "INSERT INTO elements (substation_id, element_type, name) VALUES (?, ?, ?)",
            (sid, "Μετασχηματιστής 150/20KV", name),
        )
    conn.commit()

    app = SubstationApp()
    app.conn = conn
    return app, sid


def test_get_available_gates_regular_and_inter():
    app, sid = setup_app_with_substation_and_transformers(["T1", "T2", "T3"])
    gates_both = app.get_available_gates(sid, None)
    # Assignment-safe order: unassigned, regular gates first, then interconnections.
    assert "(Μη καταχωρημένο)" in gates_both
    assert "ΠΥΛΗ 1" in gates_both
    assert "ΠΥΛΗ 2" in gates_both
    assert "ΠΥΛΗ 3" in gates_both
    assert "ΠΥΛΗ 1-2" in gates_both
    assert "ΠΥΛΗ 2-3" in gates_both
    assert gates_both[:6] == [
        "(Μη καταχωρημένο)",
        "ΠΥΛΗ 1",
        "ΠΥΛΗ 2",
        "ΠΥΛΗ 3",
        "ΠΥΛΗ 1-3",
        "ΠΥΛΗ 1-2",
    ]


def test_get_available_gates_inter_true_false():
    app, sid = setup_app_with_substation_and_transformers(["T1", "T2"])
    regular = app.get_available_gates(sid, False)
    inter = app.get_available_gates(sid, True)
    assert "ΠΥΛΗ 1" in regular and "ΠΥΛΗ 2" in regular
    assert all("-" not in g for g in regular if g != "(Μη καταχωρημένο)")
    assert "ΠΥΛΗ 1-2" in inter
    assert all("-" in g for g in inter if g != "(Μη καταχωρημένο)")


def test_get_available_gates_fills_missing_for_unassigned_transformer():
    app, sid = setup_app_with_substation_and_transformers(["T1", "T2"])
    c = app.conn.cursor()
    c.execute(
        "UPDATE elements SET gate=? WHERE substation_id=? AND name=?",
        ("ΠΥΛΗ 1", sid, "T1"),
    )
    app.conn.commit()

    regular = app.get_available_gates(sid, False)

    assert "ΠΥΛΗ 1" in regular
    assert "ΠΥΛΗ 2" in regular


def test_get_available_hemizygos_options():
    options = SubstationApp.get_available_hemizygos_options()
    assert options[0] == S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
    assert "Ημιζυγός 1" in options
    assert "Ημιζυγός 2" in options


def test_hemizygos_display_sort_key_orders_defined_groups_first():
    assert SubstationApp.hemizygos_display_sort_key(
        "Ημιζυγός 1"
    ) < SubstationApp.hemizygos_display_sort_key("Ημιζυγός 2")
    assert SubstationApp.hemizygos_display_sort_key(
        "Ημιζυγός 2"
    ) < SubstationApp.hemizygos_display_sort_key("")


def test_sort_gate_labels_for_display_requested_order():
    ordered = SubstationApp.sort_gate_labels_for_display(
        ["ΠΥΛΗ 2-3", "ΠΥΛΗ 2", "ΠΥΛΗ 1-2", "ΠΥΛΗ 3", "ΠΥΛΗ 1", "ΠΥΛΗ 1-3"]
    )
    assert ordered == ["ΠΥΛΗ 1-3", "ΠΥΛΗ 1", "ΠΥΛΗ 1-2", "ΠΥΛΗ 2", "ΠΥΛΗ 2-3", "ΠΥΛΗ 3"]


def test_init_db_adds_hemizygos_column():
    conn = init_db(":memory:")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(elements)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "hemizygos" in columns


def test_breaker_category_and_format_helpers():
    app = SubstationApp()
    # Categories
    hv_cats = app._get_breaker_categories_for_element_type(ELEM_BREAKER_YT)
    mv_cats = app._get_breaker_categories_for_element_type(ELEM_BREAKER_MT)
    assert "SF6" in hv_cats
    assert "Πτωχού Ελαίου" in mv_cats

    # Format elem type
    assert app._format_elem_type(ELEM_BREAKER_YT, 1).startswith(ELEM_BREAKER_YT)
    assert "Κεντρικός" in app._format_elem_type(ELEM_BREAKER_YT, 1)
    assert "Διασυνδετικός" in app._format_elem_type(ELEM_BREAKER_MT, 2)


def test_gate_has_transformer_elements_only_when_gate_contains_transformer():
    app = SubstationApp()

    transformer_gate = [
        (
            1,
            "Μετασχηματιστής 150/20KV",
            "T1",
            None,
            "ΠΥΛΗ 1",
            0,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            2,
            ELEM_BREAKER_MT,
            "B1",
            None,
            "ΠΥΛΗ 1",
            0,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ]
    interconnection_gate = [
        (
            3,
            ELEM_BREAKER_MT,
            "B2",
            None,
            "ΠΥΛΗ 1-2",
            2,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ]

    assert app._gate_has_transformer_elements(transformer_gate) is True
    assert app._gate_has_transformer_elements(interconnection_gate) is False


def test_sync_selected_element_details_visibility_builds_and_hides_details():
    app = SubstationApp()
    calls = []

    class DummyParent:
        def __init__(self):
            self.removed = []

        def remove_widget(self, widget):
            self.removed.append(widget)
            widget.parent = None

    class DummyCheckbox:
        def __init__(self, active):
            self.active = active

    class DummyDetails:
        def __init__(self, parent=None):
            self.parent = parent

    active_details = DummyDetails()
    inactive_parent = DummyParent()
    inactive_details = DummyDetails(parent=inactive_parent)

    element_widgets = {
        1: {
            "checkbox": DummyCheckbox(True),
            "ensure_details": lambda: calls.append("ensure-active"),
            "details_container": active_details,
        },
        2: {
            "checkbox": DummyCheckbox(False),
            "ensure_details": lambda: calls.append("ensure-inactive"),
            "details_container": inactive_details,
        },
    }

    app._sync_selected_element_details_visibility(element_widgets, [1, 2])

    assert calls == ["ensure-active"]
    assert inactive_parent.removed == [inactive_details]
    assert inactive_details.parent is None
