import sqlite3, os
import logging

# configure basic logging for script usage
logging.basicConfig(level=logging.INFO, format="%(message)s")

# default DB
candidates = [
    'substations.db',
    'substations_backup.db',
    'database.db',
    'database.py',
    'database.db',
    'substations.db.backup.20260212170622.bak',
]
found = False
for db in candidates:
    if not os.path.exists(db):
        continue
    logging.info('Trying DB: %s', db)
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='people'")
        if not cur.fetchone():
            logging.info(' No people table in %s', db)
            conn.close()
            continue
        cur.execute('SELECT COUNT(*) FROM people')
        total = cur.fetchone()[0]
        logging.info(' People rows: %s', total)
        cur.execute('SELECT DISTINCT role FROM people')
        rows = cur.fetchall()
        logging.info(' Distinct roles count: %s', len(rows))
        for r in rows:
            logging.info('  %r', r[0])
        logging.info(' Sample rows:')
        cur.execute('SELECT id, name, role FROM people LIMIT 10')
        for r in cur.fetchall():
            logging.info('  %s', r)
        conn.close()
        found = True
    except Exception as e:
        logging.exception(' Error opening %s', db)

if not found:
    logging.error('No suitable DB with people table found in candidates list')
else:
    # If we found roles, try canonical mapping
    try:
        import validation
        logging.info('\nCanonical mapping preview:')
        for db in candidates:
            if not os.path.exists(db):
                continue
            try:
                conn = sqlite3.connect(db)
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT role FROM people")
                rows = cur.fetchall()
                for r in rows:
                    logging.info(' %r -> %r', r[0], validation.canonical_role(r[0]))
                conn.close()
            except Exception:
                pass
    except Exception:
        pass
