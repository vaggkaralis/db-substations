import sqlite3, os, sys
DB='substations_backup.db'
if not os.path.exists(DB):
    print('DB not found:', DB)
    sys.exit(2)
con=sqlite3.connect(DB)
c=con.cursor()
c.execute('SELECT id,name,element_type,breaker_category FROM elements WHERE name=?', ('Ρ-225',))
row=c.fetchone()
print('element:', row)
if row:
    eid=row[0]
    c.execute('SELECT maintenance_id, vidar_fa, vidar_fb, vidar_fc FROM maintenance_elements WHERE element_id=?', (eid,))
    print('maintenance_elements:', c.fetchall())
con.close()
