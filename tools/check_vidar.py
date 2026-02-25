import logging
import os
import sqlite3
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")

DB = 'substations_backup.db'
if not os.path.exists(DB):
    logging.error('DB not found: %s', DB)
    sys.exit(2)
con = sqlite3.connect(DB)
c = con.cursor()
c.execute('SELECT id,name,element_type,breaker_category FROM elements WHERE name=?', ('Ρ-225',))
row = c.fetchone()
logging.info('element: %s', row)
if row:
    eid = row[0]
    c.execute('SELECT maintenance_id, vidar_fa, vidar_fb, vidar_fc FROM maintenance_elements WHERE element_id=?', (eid,))
    logging.info('maintenance_elements: %s', c.fetchall())
con.close()
