import sqlite3

import maintenance_email_importer as mei


def _make_conn():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.commit()
    return conn


def test_people_not_matched_from_short_prefix_words():
    conn = _make_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO people (id, name, active) VALUES (1, ?, 1)", ("Γιαννούλας Νικόλαος",))
    cur.execute("INSERT INTO people (id, name, active) VALUES (2, ?, 1)", ("Μουτσέλος Ιωάννης",))
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
    cur.execute("INSERT INTO people (id, name, active) VALUES (10, ?, 1)", ("Γιαννούλας Νικόλαος",))
    cur.execute("INSERT INTO people (id, name, active) VALUES (11, ?, 1)", ("Γιαννούλας Νικόλαος",))
    conn.commit()

    body = "Συμμετείχε ο Γιαννούλας Νικόλαος στις εργασίες συντήρησης."

    found = mei._find_people_in_body(conn, body)
    assert found == {10}


def test_people_matched_on_initial_plus_surname():
    conn = _make_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO people (id, name, active) VALUES (20, ?, 1)", ("Γιαννούλας Νικόλαος",))
    conn.commit()

    body = "Παρόντες: Ν. Γιαννούλας και το υπόλοιπο συνεργείο."

    found = mei._find_people_in_body(conn, body)
    assert found == {20}
