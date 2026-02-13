import sqlite3, os

# default DB
candidates = ['substations.db', 'substations_backup.db', 'database.db', 'database.py', 'database.db', 'substations.db.backup.20260212170622.bak']
found = False
for db in candidates:
    if not os.path.exists(db):
        continue
    print('Trying DB:', db)
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='people'")
        if not cur.fetchone():
            print(' No people table in', db)
            conn.close()
            continue
        cur.execute('SELECT COUNT(*) FROM people')
        total = cur.fetchone()[0]
        print(' People rows:', total)
        cur.execute('SELECT DISTINCT role FROM people')
        rows = cur.fetchall()
        print(' Distinct roles count:', len(rows))
        for r in rows:
            print('  ', repr(r[0]))
        print(' Sample rows:')
        cur.execute('SELECT id, name, role FROM people LIMIT 10')
        for r in cur.fetchall():
            print('  ', r)
        conn.close()
        found = True
    except Exception as e:
        print(' Error opening', db, e)

if not found:
    print('No suitable DB with people table found in candidates list')
else:
    # If we found roles, try canonical mapping
    try:
        import validation
        print('\nCanonical mapping preview:')
        for db in candidates:
            if not os.path.exists(db):
                continue
            try:
                conn = sqlite3.connect(db)
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT role FROM people")
                rows = cur.fetchall()
                for r in rows:
                    print(' ', repr(r[0]), '->', repr(validation.canonical_role(r[0])))
                conn.close()
            except Exception:
                pass
    except Exception:
        pass
