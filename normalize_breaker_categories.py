import datetime
import logging
import os
import shutil
import sqlite3

from settings import DB_PATH
from strings import STRINGS as S

logging.basicConfig(level=logging.INFO, format="%(message)s")

# derive canonical breaker element names from centralized strings when available
ELEM_BREAKER_YT = next((t for t in S["MESSAGES"].get("ELEMENT_TYPES", []) if t == "Διακόπτης ΥΤ"), "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = next((t for t in S["MESSAGES"].get("ELEMENT_TYPES", []) if t == "Διακόπτης ΜΤ"), "Διακόπτης ΜΤ")


def backup_db(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    bak = f"{path}.backup.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    shutil.copy2(path, bak)
    logging.info(S["MESSAGES"].get("BACKUP_CREATED", "backup created %s"), bak)
    return bak


def normalize():
    backup_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Map legacy english to greek
    cur.execute("UPDATE elements SET breaker_category='Ελαίου' WHERE breaker_category='Oil'")
    # Fill empty/null from element_models
    cur.execute(
        "UPDATE elements SET breaker_category=(SELECT breaker_category FROM element_models WHERE element_models.id=elements.element_model_id) WHERE (breaker_category IS NULL OR TRIM(breaker_category)='') AND element_model_id IS NOT NULL"
    )
    # If still empty, set a sensible default per element_type (SF6 for YT, Ελαίου for MT)
    cur.execute(
        f"UPDATE elements SET breaker_category='SF6' WHERE (breaker_category IS NULL OR TRIM(breaker_category)='') AND element_type='{ELEM_BREAKER_YT}'"
    )
    cur.execute(
        f"UPDATE elements SET breaker_category='Ελαίου' WHERE (breaker_category IS NULL OR TRIM(breaker_category)='') AND element_type='{ELEM_BREAKER_MT}'"
    )
    conn.commit()
    logging.info(S["MESSAGES"].get("ROWS_UPDATED", "rows updated: %s"), conn.total_changes)
    conn.close()


if __name__ == '__main__':
    normalize()
