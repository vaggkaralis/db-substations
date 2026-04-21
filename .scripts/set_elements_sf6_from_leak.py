import sqlite3
import sys
import os

sys.path.insert(0, os.getcwd())
from settings import DB_PATH  # noqa: E402

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print(
    "Scanning maintenance_elements with sf6_leakage_kg > 0 for elements not marked SF6..."
)

c.execute("""
SELECT DISTINCT e.id, e.name, e.breaker_category, e.element_type
FROM maintenance_elements me
JOIN maintenance m ON me.maintenance_id = m.id
JOIN elements e ON me.element_id = e.id
WHERE me.sf6_leakage_kg IS NOT NULL AND me.sf6_leakage_kg > 0
""")
rows = c.fetchall()

candidates = [r for r in rows if (r[2] or "") != "SF6"]
print(
    "Found",
    len(rows),
    "elements with leakage records;",
    len(candidates),
    "not marked SF6",
)
for r in candidates[:200]:
    print(r)

if candidates:
    ids = [str(r[0]) for r in candidates]
    print("\nUpdating elements IDs to breaker_category='SF6'...")
    q = f"UPDATE elements SET breaker_category='SF6' WHERE id IN ({','.join(ids)})"
    c.execute(q)
    conn.commit()
    print("Update committed.")

# Verify
c.execute("SELECT COUNT(*) FROM elements WHERE breaker_category='SF6'")
count_sf6 = c.fetchone()[0]
print("\nTotal elements with breaker_category=SF6 now:", count_sf6)

conn.close()
print("Done.")
