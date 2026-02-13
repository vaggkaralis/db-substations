#!/usr/bin/env python3
import sqlite3
import sys

name = sys.argv[1] if len(sys.argv) > 1 else 'Ρ-15'
sub = sys.argv[2] if len(sys.argv) > 2 else None

con = sqlite3.connect('substations.db')
cur = con.cursor()
if sub:
    cur.execute("SELECT e.id,e.name,e.element_type,e.breaker_category,s.name FROM elements e JOIN substations s ON e.substation_id=s.id WHERE s.name LIKE ? COLLATE NOCASE AND e.name LIKE ? COLLATE NOCASE", (f'%{sub}%', f'%{name}%'))
else:
    cur.execute("SELECT id,name,element_type,breaker_category,substation_id FROM elements WHERE name LIKE ? COLLATE NOCASE", (f'%{name}%',))
rows = cur.fetchall()
if not rows:
    print('No rows found')
else:
    for r in rows:
        print(r)
con.close()
