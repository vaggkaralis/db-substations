import json
import shutil
import sqlite3
import sys
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pyodbc


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from settings import DB_PATH  # noqa: E402


SQLITE_PATH = ROOT_DIR / DB_PATH
ACCDB_PATH = ROOT_DIR / "substation_asset_maintenance.accdb"
BACKUP_DIR = ROOT_DIR / "backups" / "access_imports"
REPORT_PATH = ROOT_DIR / "reports" / "access_model_attributes_report.json"

ELEM_BREAKER_YT = "Διακόπτης ΥΤ"
ELEM_BREAKER_MT = "Διακόπτης ΜΤ"
ELEM_BREAKER_YT_EN = "HV Breaker"
ELEM_BREAKER_MT_EN = "MV Breaker"

REQUIRED_COLUMNS = {
    "connection_group": "TEXT",
    "rated_voltage_hv_lv": "TEXT",
    "mounting": "TEXT",
    "specification": "TEXT",
    "bil_hv_lv_kv": "TEXT",
    "total_weight_kg": "REAL",
    "oil_weight_kg": "REAL",
    "rated_normal_current_a": "REAL",
    "rated_short_circuit_breaking_current_ka": "REAL",
    "short_circuit_duration_s": "REAL",
    "making_capacity_ka": "REAL",
    "sf6_pressure_rated_bar": "REAL",
    "drive_mechanism": "TEXT",
    "rated_short_circuit_making_current_ka": "REAL",
    "cubicle": "TEXT",
}


def normalize_text(value):
    text = str(value or "").replace("\x00", " ").strip().upper()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = (
        text.replace("Α", "A")
        .replace("Β", "B")
        .replace("Ε", "E")
        .replace("Η", "H")
        .replace("Ι", "I")
        .replace("Κ", "K")
        .replace("Μ", "M")
        .replace("Ν", "N")
        .replace("Ο", "O")
        .replace("Ρ", "P")
        .replace("Τ", "T")
        .replace("Υ", "Y")
        .replace("Χ", "X")
    )
    cleaned = []
    for ch in text:
        cleaned.append(ch if ch.isalnum() else " ")
    return " ".join("".join(cleaned).split())


def text_similarity(left, right):
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def parse_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def normalize_transformer_weight(value):
    parsed = parse_float(value)
    if parsed is None:
        return None
    if 0 < parsed < 1000:
        return parsed * 1000.0
    return parsed


def backup_sqlite_db():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIR / f"substations_before_access_model_attributes_{timestamp}.db"
    )
    shutil.copy2(SQLITE_PATH, backup_path)
    return backup_path


def ensure_columns(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(element_models)")
    existing = {row[1] for row in cursor.fetchall()}
    for column_name, column_type in REQUIRED_COLUMNS.items():
        if column_name in existing:
            continue
        cursor.execute(
            f"ALTER TABLE element_models ADD COLUMN {column_name} {column_type}"
        )
    conn.commit()


def category_kind(category):
    text = str(category or "")
    if "150/20" in text:
        return "transformer"
    normalized = normalize_text(text)
    if normalized in {
        normalize_text(ELEM_BREAKER_YT),
        normalize_text(ELEM_BREAKER_YT_EN),
    }:
        return "hv_breaker"
    if normalized in {
        normalize_text(ELEM_BREAKER_MT),
        normalize_text(ELEM_BREAKER_MT_EN),
    }:
        return "mv_breaker"
    return None


def build_access_connection():
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};" + f"DBQ={ACCDB_PATH};"
    )
    return pyodbc.connect(conn_str)


def load_transformer_models(cursor):
    rows = cursor.execute("SELECT * FROM [tblPowerTransformersModel]").fetchall()
    models = []
    for row in rows:
        models.append(
            {
                "source_table": "tblPowerTransformersModel",
                "source_id": row[0],
                "manufacturer": row[1],
                "model_name": row[2],
                "connection_group": row[4],
                "rated_voltage_hv_lv": row[8],
                "mounting": row[9],
                "specification": row[11],
                "bil_hv_lv_kv": row[16],
                "oil_weight_kg": normalize_transformer_weight(row[18]),
                "total_weight_kg": normalize_transformer_weight(row[21]),
            }
        )
    return models


def load_hv_breaker_models(cursor):
    rows = cursor.execute("SELECT * FROM [tblHVCBModel]").fetchall()
    models = []
    for row in rows:
        models.append(
            {
                "source_table": "tblHVCBModel",
                "source_id": row[0],
                "manufacturer": row[1],
                "model_name": row[2],
                "rated_normal_current_a": parse_float(row[9]),
                "rated_short_circuit_breaking_current_ka": parse_float(row[11]),
                "short_circuit_duration_s": parse_float(row[10]),
                "making_capacity_ka": parse_float(row[14]),
                "sf6_pressure_rated_bar": parse_float(row[22]),
                "total_weight_kg": parse_float(row[29]),
                "drive_mechanism": row[28],
            }
        )
    return models


def load_mv_breaker_models(cursor):
    rows = cursor.execute("SELECT * FROM [tblMVCBModel]").fetchall()
    models = []
    for row in rows:
        models.append(
            {
                "source_table": "tblMVCBModel",
                "source_id": row[0],
                "manufacturer": row[1],
                "model_name": row[4],
                "rated_normal_current_a": parse_float(row[7]),
                "rated_short_circuit_breaking_current_ka": parse_float(row[8]),
                "short_circuit_duration_s": parse_float(row[9]),
                "rated_short_circuit_making_current_ka": parse_float(row[10]),
                "cubicle": None if row[6] in (False, None, "") else str(row[6]),
                "total_weight_kg": parse_float(row[23]),
            }
        )
    return models


def score_candidate(local_model, access_model):
    local_manufacturer = normalize_text(local_model["manufacturer"])
    local_name = normalize_text(local_model["model_name"])
    access_manufacturer = normalize_text(access_model.get("manufacturer"))
    access_name = normalize_text(access_model.get("model_name"))

    score = 0.0
    if (
        local_manufacturer
        and access_manufacturer
        and local_manufacturer == access_manufacturer
    ):
        score += 3.0
    if local_name and access_name:
        if access_name in local_name or local_name in access_name:
            score += 5.0
        score += text_similarity(local_name, access_name) * 4.0

        local_numbers = set(part for part in local_name.split() if part.isdigit())
        access_numbers = set(part for part in access_name.split() if part.isdigit())
        score += float(len(local_numbers & access_numbers))

    return score


def best_match(local_model, access_models):
    ranked = []
    for candidate in access_models:
        score = score_candidate(local_model, candidate)
        if score > 0:
            ranked.append((score, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1]["source_id"]))
    if not ranked:
        return None, []

    best_score, best_candidate = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else None
    if best_score < 6.0:
        return None, ranked[:5]
    if second_score is not None and best_score - second_score < 1.0:
        return None, ranked[:5]
    return best_candidate, ranked[:5]


def local_models(conn):
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT * FROM element_models ORDER BY element_category, model_name"
    ).fetchall()
    return [dict(row) for row in rows]


def apply_updates(conn, models, access_groups):
    cursor = conn.cursor()
    updates = []
    unmatched = []
    skipped = []

    for model in models:
        kind = category_kind(model.get("element_category"))
        if not kind:
            continue

        access_model, ranked = best_match(model, access_groups[kind])
        if access_model is None:
            unmatched.append(
                {
                    "id": model["id"],
                    "element_category": model.get("element_category"),
                    "model_name": model.get("model_name"),
                    "manufacturer": model.get("manufacturer"),
                    "candidates": [
                        {
                            "score": round(score, 3),
                            "source_id": candidate["source_id"],
                            "source_table": candidate["source_table"],
                            "manufacturer": candidate.get("manufacturer"),
                            "model_name": candidate.get("model_name"),
                        }
                        for score, candidate in ranked
                    ],
                }
            )
            continue

        changed_fields = {}
        for column_name in REQUIRED_COLUMNS:
            local_value = model.get(column_name)
            access_value = access_model.get(column_name)
            if access_value in (None, ""):
                continue
            if local_value not in (None, ""):
                continue
            changed_fields[column_name] = access_value

        if not changed_fields:
            skipped.append(
                {
                    "id": model["id"],
                    "model_name": model.get("model_name"),
                    "manufacturer": model.get("manufacturer"),
                    "reason": "No empty target fields matched populated Access data.",
                    "source_table": access_model["source_table"],
                    "source_id": access_model["source_id"],
                }
            )
            continue

        set_clause = ", ".join(f"{column_name}=?" for column_name in changed_fields)
        cursor.execute(
            f"UPDATE element_models SET {set_clause} WHERE id=?",
            list(changed_fields.values()) + [model["id"]],
        )
        updates.append(
            {
                "id": model["id"],
                "element_category": model.get("element_category"),
                "model_name": model.get("model_name"),
                "manufacturer": model.get("manufacturer"),
                "source_table": access_model["source_table"],
                "source_id": access_model["source_id"],
                "updated_fields": changed_fields,
            }
        )

    conn.commit()
    return updates, unmatched, skipped


def main():
    backup_path = backup_sqlite_db()
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    ensure_columns(sqlite_conn)

    access_conn = build_access_connection()
    access_cursor = access_conn.cursor()
    access_groups = {
        "transformer": load_transformer_models(access_cursor),
        "hv_breaker": load_hv_breaker_models(access_cursor),
        "mv_breaker": load_mv_breaker_models(access_cursor),
    }

    updates, unmatched, skipped = apply_updates(
        sqlite_conn, local_models(sqlite_conn), access_groups
    )
    sqlite_conn.close()
    access_conn.close()

    report = {
        "backup_path": str(backup_path),
        "sqlite_path": str(SQLITE_PATH),
        "access_path": str(ACCDB_PATH),
        "updated_models": len(updates),
        "unmatched_models": len(unmatched),
        "skipped_models": len(skipped),
        "updates": updates,
        "unmatched": unmatched,
        "skipped": skipped,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
