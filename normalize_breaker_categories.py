import shutil
import sqlite3
import os
import datetime

from settings import DB_PATH

def backup_db(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    bak = f"{path}.backup.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    shutil.copy2(path, bak)
    print('backup created', bak)
    return bak


def normalize():
    bak = backup_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Map legacy english to greek
    cur.execute("UPDATE elements SET breaker_category='Ελαίου' WHERE breaker_category='Oil'")
    # Fill empty/null from element_models
    cur.execute(
        "UPDATE elements SET breaker_category=(SELECT breaker_category FROM element_models WHERE element_models.id=elements.element_model_id) WHERE (breaker_category IS NULL OR TRIM(breaker_category)='') AND element_model_id IS NOT NULL"
    )
    # If still empty, set a sensible default per element_type (SF6 for YT, Ελαίου for others is risky)
    cur.execute(
        "UPDATE elements SET breaker_category='SF6' WHERE (breaker_category IS NULL OR TRIM(breaker_category)='') AND element_type='Διακόπτης ΥΤ'"
    )
    cur.execute(
        "UPDATE elements SET breaker_category='Ελαίου' WHERE (breaker_category IS NULL OR TRIM(breaker_category)='') AND element_type='Διακόπτης ΜΤ'"
    )
    conn.commit()
    print('rows updated:', conn.total_changes)
    conn.close()

if __name__ == '__main__':
    normalize()
