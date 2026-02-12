import sqlite3
from database import init_db
from DBrun import SubstationApp


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
    # Expect regular 1..3 and inter 1-2,2-3, plus the unassigned option
    assert "(Μη καταχωρημένο)" in gates_both
    assert "ΠΥΛΗ 1" in gates_both
    assert "ΠΥΛΗ 2" in gates_both
    assert "ΠΥΛΗ 3" in gates_both
    assert "ΠΥΛΗ 1-2" in gates_both
    assert "ΠΥΛΗ 2-3" in gates_both


def test_get_available_gates_inter_true_false():
    app, sid = setup_app_with_substation_and_transformers(["T1", "T2"])
    regular = app.get_available_gates(sid, False)
    inter = app.get_available_gates(sid, True)
    assert "ΠΥΛΗ 1" in regular and "ΠΥΛΗ 2" in regular
    assert all("-" not in g for g in regular if g != "(Μη καταχωρημένο)")
    assert "ΠΥΛΗ 1-2" in inter
    assert all("-" in g for g in inter if g != "(Μη καταχωρημένο)")


def test_breaker_category_and_format_helpers():
    app = SubstationApp()
    # Categories
    hv_cats = app._get_breaker_categories_for_element_type("Διακόπτης ΥΤ")
    mv_cats = app._get_breaker_categories_for_element_type("Διακόπτης ΜΤ")
    assert "SF6" in hv_cats
    assert "Πτωχού Ελαίου" in mv_cats

    # Format elem type
    assert app._format_elem_type("Διακόπτης ΥΤ", 1).startswith("Διακόπτης ΥΤ")
    assert "Κεντρικός" in app._format_elem_type("Διακόπτης ΥΤ", 1)
    assert "Διασυνδετικός" in app._format_elem_type("Διακόπτης ΜΤ", 2)
