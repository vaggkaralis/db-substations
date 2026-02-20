import inspections
import sqlite3
class D:
    pass

if __name__ == '__main__':
    d = D()
    d.conn = sqlite3.connect(':memory:')
    inspections.handle_inspection_history(d)
    print('OK')
