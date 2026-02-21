#!/usr/bin/env python3
"""Normalize breaker_category values in the DB (one-time migration).

Creates a timestamped backup of the DB before applying changes.
Uses `import_validator.validate_breaker_category` to map variants to canonical keys.
"""
import os
import shutil
import sqlite3
from datetime import datetime

from strings import STRINGS as S

# derive canonical breaker element names from centralized strings when available
ELEM_BREAKER_YT = next((t for t in S["MESSAGES"].get("ELEMENT_TYPES", []) if t == "Διακόπτης ΥΤ"), "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = next((t for t in S["MESSAGES"].get("ELEMENT_TYPES", []) if t == "Διακόπτης ΜΤ"), "Διακόπτης ΜΤ")

try:
    from settings import DB_PATH
except Exception:
    DB_PATH = "substations.db"

def backup_db(path):
    if not os.path.exists(path):
        print(S["MESSAGES"].get("DB_NOT_FOUND", "DB not found: {path}").format(path=path))
        return None
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    bak = f"{path}.breakercat_migration.{ts}.bak"
    shutil.copy2(path, bak)
    return bak

def normalize_breaker_categories(conn):
    try:
        from import_validator import validate_breaker_category
    except Exception:
        validate_breaker_category = None

    cursor = conn.cursor()

    # Normalize element_models.breaker_category for breaker model categories
    cursor.execute("SELECT DISTINCT breaker_category, element_category FROM element_models")
    models = cursor.fetchall()
    for bc, elem_cat in models:
        if not bc or str(bc).strip() == "":
            continue
        val = str(bc).strip()
        canon = None
        if validate_breaker_category:
            try:
                res = validate_breaker_category(val)
                if res and res[0]:
                    canon = res[0]
            except Exception:
                canon = None
        if not canon:
            # simple normalization heuristics
            v = val.lower().replace(" ", "")
            if v in ("sf6", "sf-6"):
                canon = "SF6"
            elif v in ("vacuum",):
                # VACUUM mapping depends on element category (MV/HV)
                if elem_cat == 'Διακόπτης ΥΤ':
                    canon = 'Ελαίου'
                else:
                    canon = 'Κενού'
            elif v in ("oil",):
                canon = 'Ελαίου'
            elif v in ("minimumoil", "minimumoil", "lowoil"):
                canon = 'Πτωχού Ελαίου'

        if canon and canon != val:
            print(S["MESSAGES"].get("UPDATING_ELEMENT_MODELS", "Updating element_models: '{old}' -> '{new}' (element_category={elem_cat})").format(old=val, new=canon, elem_cat=elem_cat))
            cursor.execute(
                "UPDATE element_models SET breaker_category=? WHERE breaker_category=? AND (element_category=? OR ? IS NULL)",
                (canon, val, elem_cat, elem_cat),
            )

    # Normalize elements.breaker_category for existing element rows
    cursor.execute("SELECT DISTINCT breaker_category, element_type FROM elements")
    elems = cursor.fetchall()
    for bc, elem_type in elems:
        if not bc or str(bc).strip() == "":
            continue
        val = str(bc).strip()
        canon = None
        if validate_breaker_category:
            try:
                res = validate_breaker_category(val)
                if res and res[0]:
                    canon = res[0]
            except Exception:
                canon = None
        if not canon:
            v = val.lower().replace(" ", "")
            if v in ("sf6", "sf-6"):
                canon = "SF6"
            elif v in ("vacuum",):
                if elem_type == 'Διακόπτης ΥΤ':
                    canon = 'Ελαίου'
                else:
                    canon = 'Κενού'
            elif v in ("oil",):
                canon = 'Ελαίου'
            elif v in ("minimumoil", "lowoil"):
                canon = 'Πτωχού Ελαίου'

        if canon and canon != val:
            print(S["MESSAGES"].get("UPDATING_ELEMENTS", "Updating elements: '{old}' -> '{new}' (element_type={elem_type})").format(old=val, new=canon, elem_type=elem_type))
            cursor.execute(
                "UPDATE elements SET breaker_category=? WHERE breaker_category=? AND (element_type=? OR ? IS NULL)",
                (canon, val, elem_type, elem_type),
            )

    conn.commit()

def main():
    print(S["MESSAGES"].get("DB_PATH_LABEL", "DB path: {path}").format(path=DB_PATH))
    bak = backup_db(DB_PATH)
    if bak:
        print(S["MESSAGES"].get("BACKUP_CREATED", "Backup created: {bak}").format(bak=bak))
    else:
        print(S["MESSAGES"].get("NO_BACKUP_ABORT", "No backup created; aborting."))
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        normalize_breaker_categories(conn)
        print(S["MESSAGES"].get("NORMALIZATION_COMPLETE", "Normalization complete."))
    except Exception as e:
        print(S["MESSAGES"].get("MIGRATION_FAILED", "Migration failed: {err}").format(err=e))
    finally:
        conn.close()

if __name__ == '__main__':
    main()
