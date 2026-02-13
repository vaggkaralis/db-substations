#!/usr/bin/env python3
"""Repair elements in substations_backup.db:
- Ensure each element has a unique, non-zero `id`.
- Fix invalid `element_type` or `breaker_category` values by assigning a random valid one.

Run as: python tools/repair_elements_db.py [path_to_db]
"""
import sqlite3
import sys
import os
import random

DB = sys.argv[1] if len(sys.argv) > 1 else "substations_backup.db"

if not os.path.exists(DB):
    print("Database not found:", DB)
    sys.exit(2)

try:
    # Import lightweight mappings from import_validator
    from import_validator import ELEMENT_TYPE_MAPPINGS, BREAKER_CATEGORY_MAPPINGS
except Exception:
    # Fallback conservative sets
    ELEMENT_TYPE_MAPPINGS = {
        "Διακόπτης ΥΤ": [],
        "Διακόπτης ΜΤ": [],
        "Μετασχηματιστής 150/20KV": [],
        "Μετασχηματιστής 20/0.4KV": [],
    }
    BREAKER_CATEGORY_MAPPINGS = {"SF6": [], "Πτωχού Ελαίου": [], "Ελαίου": [], "Κενού": []}

# Allowed categories per element type (business rule)
ALLOWED_BREAKER_CATEGORIES = {
    "Διακόπτης ΥΤ": ["SF6", "Ελαίου"],
    "Διακόπτης ΜΤ": ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"],
}

allowed_element_types = list(ELEMENT_TYPE_MAPPINGS.keys()) if ELEMENT_TYPE_MAPPINGS else list(ALLOWED_BREAKER_CATEGORIES.keys())
allowed_breakers_all = list(BREAKER_CATEGORY_MAPPINGS.keys()) if BREAKER_CATEGORY_MAPPINGS else ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"]

con = sqlite3.connect(DB)
cur = con.cursor()

def fetch_elements():
    cur.execute("SELECT rowid, id, name, element_type, breaker_category FROM elements")
    return cur.fetchall()

elements = fetch_elements()
if not elements:
    print("No elements found in database.")
    con.close()
    sys.exit(0)

max_id = 0
cur.execute("SELECT MAX(id) FROM elements")
res = cur.fetchone()
if res and res[0]:
    try:
        max_id = int(res[0])
    except Exception:
        max_id = 0

changed = 0
assigned_ids = set()
for row in elements:
    rowid, eid, name, elem_type, breaker = row
    # Ensure id exists and is positive integer
    if not eid or eid == 0:
        max_id += 1
        new_id = max_id
        cur.execute("UPDATE elements SET id=? WHERE rowid=?", (new_id, rowid))
        eid = new_id
        changed += 1
        print(f"Assigned id={new_id} to element rowid={rowid} name={name}")
    # Uniqueness (collect)
    if eid in assigned_ids:
        # Rare: duplicate id, assign new
        max_id += 1
        new_id = max_id
        cur.execute("UPDATE elements SET id=? WHERE rowid=?", (new_id, rowid))
        eid = new_id
        changed += 1
        print(f"Reassigned duplicate id -> id={new_id} for element {name} (rowid={rowid})")
    assigned_ids.add(eid)

    # Validate element_type
    if elem_type not in allowed_element_types:
        new_type = random.choice(allowed_element_types)
        cur.execute("UPDATE elements SET element_type=? WHERE id=?", (new_type, eid))
        changed += 1
        print(f"Fixed element_type for id={eid} from '{elem_type}' -> '{new_type}'")
        elem_type = new_type

    # Validate breaker_category according to element type
    allowed_for_type = ALLOWED_BREAKER_CATEGORIES.get(elem_type, allowed_breakers_all)
    if breaker not in allowed_for_type:
        new_breaker = random.choice(allowed_for_type)
        cur.execute("UPDATE elements SET breaker_category=? WHERE id=?", (new_breaker, eid))
        changed += 1
        print(f"Fixed breaker_category for id={eid} from '{breaker}' -> '{new_breaker}'")

con.commit()
print(f"Completed repairs. Total changes: {changed}")
con.close()

if changed == 0:
    print("No repairs needed.")
