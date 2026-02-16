import traceback
import sys

try:
    import DBrun
except Exception:
    with open('startup_error.log', 'w', encoding='utf-8') as f:
        traceback.print_exc(file=f)
    print('Error written to startup_error.log')
    sys.exit(1)
else:
    print('DBrun imported without exception')
