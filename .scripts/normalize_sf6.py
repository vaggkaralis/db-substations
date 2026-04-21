import sqlite3
import re
import sys
import os

# Ensure project root is on sys.path so imports like `from settings import DB_PATH` work
sys.path.insert(0, os.getcwd())
from settings import DB_PATH  # noqa: E402

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print("Connected to DB:", DB_PATH)

# List distinct breaker_category values and counts
c.execute(
    "SELECT COALESCE(breaker_category,''), COUNT(*) FROM elements GROUP BY COALESCE(breaker_category,'') ORDER BY COUNT(*) DESC"
)
dist = c.fetchall()
print("Distinct breaker_category values and counts:")
for v, cnt in dist:
    print(repr(v), cnt)


# Identify candidate element ids where breaker_category looks like SF6 but not canonical 'SF6'
def norm(s):
    return re.sub(r"[^A-Za-z0-9]", "", (s or "").lower())


c.execute("SELECT id, name, breaker_category FROM elements")
rows = c.fetchall()
candidates = [r for r in rows if norm(r[2]) == "sf6" and (r[2] or "") != "SF6"]
print("\nCandidates to update to SF6:", len(candidates))
for r in candidates[:200]:
    print(r)

# Apply update if any
if candidates:
    ids = [str(r[0]) for r in candidates]
    print("\nApplying update to", len(ids), "rows...")
    q = f"UPDATE elements SET breaker_category = 'SF6' WHERE id IN ({','.join(ids)})"
    c.execute(q)
    conn.commit()
    print("Update committed.")

# Verify all SF6-normalized rows now exact 'SF6'
c.execute(
    "SELECT COUNT(*) FROM elements WHERE (UPPER(REPLACE(REPLACE(REPLACE(COALESCE(breaker_category,''),' ',''),'-',''),'\t',''))) = 'SF6'"
)
count_sf6 = c.fetchone()[0]
print("\nRows matching normalized SF6:", count_sf6)

# Show remaining distinct values after update
c.execute(
    "SELECT COALESCE(breaker_category,''), COUNT(*) FROM elements GROUP BY COALESCE(breaker_category,'') ORDER BY COUNT(*) DESC"
)
dist2 = c.fetchall()
print("\nDistinct breaker_category values after update:")
for v, cnt in dist2:
    print(repr(v), cnt)

conn.close()
print("\nDone.")
