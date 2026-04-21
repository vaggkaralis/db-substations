import sqlite3
import os
import sys

sys.path.insert(0, os.getcwd())
from settings import DB_PATH  # noqa: E402

ALLOWED = {"SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού", ""}
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute(
    "SELECT COALESCE(breaker_category,''), COUNT(*) FROM elements GROUP BY COALESCE(breaker_category,'') ORDER BY COUNT(*) DESC"
)
d = c.fetchall()
print("Distinct values and counts:")
for v, cnt in d:
    print(repr(v), cnt)

invalid = [(v, cnt) for (v, cnt) in d if v not in ALLOWED]
print("\nInvalid/Unexpected values:")
for v, cnt in invalid:
    print(repr(v), cnt)

# Show sample element ids for any invalid values
for v, cnt in invalid:
    print("\nSample rows for", repr(v))
    c.execute(
        "SELECT id, name, element_type FROM elements WHERE COALESCE(breaker_category,'') = ? LIMIT 20",
        (v,),
    )
    for r in c.fetchall():
        print(r)

conn.close()
print("\nDone.")
