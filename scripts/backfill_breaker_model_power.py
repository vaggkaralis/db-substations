import sqlite3
from pathlib import Path

from breaker_model_utils import (
    ELEM_BREAKER_MT,
    ELEM_BREAKER_YT,
    infer_breaker_model_values,
)
from settings import DB_PATH


ROOT_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT_DIR / DB_PATH


def main():
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, element_category, model_name, rated_normal_current_a, power_mva
        FROM element_models
        WHERE element_category IN (?, ?)
        ORDER BY id
        """,
        (ELEM_BREAKER_YT, ELEM_BREAKER_MT),
    )

    updated_models = 0
    updated_elements = 0
    for model_id, category, model_name, rated_current, power_mva in cur.fetchall():
        inferred_current, inferred_power = infer_breaker_model_values(
            category, model_name, rated_current
        )
        if inferred_current is None and inferred_power is None:
            continue

        current_changed = rated_current != inferred_current
        power_changed = power_mva != inferred_power
        if not current_changed and not power_changed:
            continue

        cur.execute(
            "UPDATE element_models SET rated_normal_current_a=?, power_mva=? WHERE id=?",
            (inferred_current, inferred_power, model_id),
        )
        updated_models += cur.rowcount

        cur.execute(
            "UPDATE elements SET power_mva=? WHERE element_model_id=?",
            (inferred_power, model_id),
        )
        updated_elements += cur.rowcount

    conn.commit()
    conn.close()
    print(
        f"Updated {updated_models} breaker models and {updated_elements} linked elements in {SQLITE_PATH.name}."
    )


if __name__ == "__main__":
    main()
