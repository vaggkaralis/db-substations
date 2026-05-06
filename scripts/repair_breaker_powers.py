"""Repair script: reconcile MV/HV breaker model power and linked element power.

This script will:
 - make a timestamped backup copy of substations.db
 - for each breaker model (element_category in breaker types), compute inferred
   power_mva using `infer_breaker_model_values`
 - if the model's stored power_mva differs from the inferred value, update it
 - update all elements linked to that model to use the inferred power_mva

Run from the project root: `.venv\Scripts\python.exe scripts\repair_breaker_powers.py`
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Ensure repo root is on sys.path so top-level modules can be imported when the
# script is invoked directly from the `scripts/` folder or elsewhere.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from breaker_model_utils import (
    infer_breaker_model_values,
    ELEM_BREAKER_MT,
    ELEM_BREAKER_YT,
)


DB = Path("substations.db")
BACKUP_DIR = Path("backups_auto")
BACKUP_DIR.mkdir(exist_ok=True)


def backup_db(db_path: Path) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"substations.db.bak.{ts}"
    shutil.copy2(db_path, dest)
    return dest


def coerce_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def main(dry_run=False):
    if not DB.exists():
        print(f"Database not found at {DB}. Aborting.")
        return 1

    backup = backup_db(DB)
    print(f"Backup created: {backup}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    breaker_categories = (ELEM_BREAKER_MT, ELEM_BREAKER_YT)
    cur.execute(
        "SELECT id, element_category, model_name, rated_normal_current_a, power_mva FROM element_models WHERE element_category IN (?, ?) ORDER BY id",
        breaker_categories,
    )

    models = cur.fetchall()
    total_models = len(models)
    model_updates = 0
    element_updates = 0

    for m in models:
        model_id = m["id"]
        category = m["element_category"]
        model_name = m["model_name"] or ""
        rated_current = coerce_float(m["rated_normal_current_a"])
        stored_model_power = coerce_float(m["power_mva"])

        inferred_current, inferred_power = infer_breaker_model_values(
            category, model_name, rated_current
        )

        if inferred_power is None:
            # nothing to infer for this model
            continue

        # if model power differs, update
        if (
            stored_model_power is None
            or abs(stored_model_power - inferred_power) > 0.0005
        ):
            print(
                f"Model {model_id}: stored power={stored_model_power} -> inferred={inferred_power}"
            )
            if not dry_run:
                cur.execute(
                    "UPDATE element_models SET power_mva=? WHERE id=?",
                    (inferred_power, model_id),
                )
                model_updates += 1

        # update linked elements
        cur.execute(
            "SELECT id, power_mva FROM elements WHERE element_model_id=?", (model_id,)
        )
        linked = cur.fetchall()
        for e in linked:
            eid = e["id"]
            epow = coerce_float(e["power_mva"])
            if epow is None or abs(epow - inferred_power) > 0.0005:
                print(f"  Element {eid}: stored={epow} -> inferred={inferred_power}")
                if not dry_run:
                    cur.execute(
                        "UPDATE elements SET power_mva=? WHERE id=?",
                        (inferred_power, eid),
                    )
                    element_updates += 1

    if not dry_run:
        conn.commit()

    conn.close()

    print(
        f"Processed {total_models} breaker models; model_updates={model_updates}; element_updates={element_updates}"
    )
    return 0


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--dry-run", action="store_true", help="Don't write changes; just report"
    )
    args = p.parse_args()
    raise SystemExit(main(dry_run=args.dry_run))
