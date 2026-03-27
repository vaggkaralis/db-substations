import sqlite3

import maintenance_email_importer as mei


def _make_conn():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """)
    conn.commit()
    return conn


def test_people_not_matched_from_short_prefix_words():
    conn = _make_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO people (id, name, active) VALUES (1, ?, 1)",
        ("Γιαννούλας Νικόλαος",),
    )
    cur.execute(
        "INSERT INTO people (id, name, active) VALUES (2, ?, 1)", ("Μουτσέλος Ιωάννης",)
    )
    conn.commit()

    body = (
        "Σχόλια: Οι μπαταρίες του Υποσταθμού έχουν διάβρωση. "
        "Θεωρώ πως καλό είναι να ειδοποιήσουμε τον ΑΔΜΗΕ."
    )

    found = mei._find_people_in_body(conn, body)
    assert found == set()


def test_people_matched_on_full_name_and_collapsed_by_display_name():
    conn = _make_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO people (id, name, active) VALUES (10, ?, 1)",
        ("Γιαννούλας Νικόλαος",),
    )
    cur.execute(
        "INSERT INTO people (id, name, active) VALUES (11, ?, 1)",
        ("Γιαννούλας Νικόλαος",),
    )
    conn.commit()

    body = "Συμμετείχε ο Γιαννούλας Νικόλαος στις εργασίες συντήρησης."

    found = mei._find_people_in_body(conn, body)
    assert found == {10}


def test_people_matched_on_initial_plus_surname():
    conn = _make_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO people (id, name, active) VALUES (20, ?, 1)",
        ("Γιαννούλας Νικόλαος",),
    )
    conn.commit()

    body = "Παρόντες: Ν. Γιαννούλας και το υπόλοιπο συνεργείο."

    found = mei._find_people_in_body(conn, body)
    assert found == {20}


def _make_element_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            element_type TEXT NOT NULL
        )
        """)
    conn.commit()
    return conn


def test_element_matching_prefers_exact_designator_over_prefix_match():
    conn = _make_element_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO elements (id, substation_id, name, element_type) VALUES (1, 1, ?, ?)",
        ("Ρ-25", "Διακόπτης ΥΤ"),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, name, element_type) VALUES (2, 1, ?, ?)",
        ("Ρ-255", "Διακόπτης ΥΤ"),
    )
    conn.commit()

    body = "Εργασίες συντήρησης πραγματοποιήθηκαν στον διακόπτη Ρ-255."

    found = mei._find_elements_in_body(conn, body, 1)
    assert found == {2}


def test_element_matching_uses_real_email_formats_without_matching_generic_ms_text():
    conn = _make_element_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO elements (id, substation_id, name, element_type) VALUES (1, 1, ?, ?)",
        ("Ρ-25", "Διακόπτης ΥΤ"),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, name, element_type) VALUES (2, 1, ?, ?)",
        ("Ρ-255", "Διακόπτης ΜΤ"),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, name, element_type) VALUES (3, 1, ?, ?)",
        ("ΜΣ1", "Μετασχηματιστής 150/20KV"),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, name, element_type) VALUES (4, 1, ?, ?)",
        ("ΜΣ2", "Μετασχηματιστής 150/20KV"),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, name, element_type) VALUES (5, 1, ?, ?)",
        ("Α/Ζ393", "Αλεξικέραυνο"),
    )
    conn.commit()

    body = """Καλησπέρα,

Σήμερα στον υποσταθμό Διδυμοτείχου έγιναν οι εξής εργασίες:

*
Αντιμετώπιση προβλήματος με το πηνίο του Ρ255. Όντως το πρόβλημα βρισκόταν στο 52αα όπως μας υπέδειξε ο κ. Ιορδανίδης. Δεν έκλεινε καμία από τις δύο επαφές του κατά τον χειρισμό του διακόπτη. Το βγάλαμε από την θέση του, καθαρίσαμε τις επαφές και στραβωσαμε ένα λαμακι για να κλείνει σωστά η επαφή. Έπειτα ο διακόπτης λειτούργησε κανονικά, τοπικά και εξ αποστάσεως με χειρισμό από κεδδ.
*
Αντικατάσταση μονωτηρα στους Α/Ζ393.
*
Πάρθηκαν δείγματα λαδιού από τους δύο ΜΣ.
*
Βγήκαν οι γειώσεις από το δίκτυο.
*
Η ηλεκτριση έγινε καλώς.

Το συνεργείο έχει 1 ώρα υπερεργασίας."""

    found = mei._find_elements_in_body(conn, body, 1)
    assert found == {2}
