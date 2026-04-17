import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

import pyodbc

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from maintenance_email_importer import _find_people_in_body  # noqa: E402
from access_gate_utils import (  # noqa: E402
    build_access_asset_gate_maps,
    find_hv_gate,
    find_mv_gate,
    find_transformer_gate,
    format_gate_label,
)

ACCDB_PATH = Path(
    r"C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations\substation_asset_maintenance.accdb"
)
SQLITE_PATH = Path(
    r"C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations\substations.db"
)
REPORT_PATH = SQLITE_PATH.parent / "reports" / "access_updates_report.json"
BACKUP_DIR = SQLITE_PATH.parent / "backups" / "access_imports"


ACCESS_TO_SQLITE_SUBSTATION = {
    "ΑΓΙΟΣ ΔΗΜΗΤΡΙΟΣ": "ΘΕΣΣΑΛΟΝΙΚΗ ΙΙΙ ΑΓ ΔΗΜΗΤΡΙΟΣ",
    "ΔΟΞΑ": "ΔΟΞΑ ΘΕΣΣΑΛΟΝΙΚΗ I",
    "ΛΗΤΗ": "ΛΗΤΗ ΛΑΓΚΑΔΑΣ",
    "ΠΤΟΛΕΜΑΙΔΑ": "ΑΗΣ ΠΤΟΛΕΜΑΙΔΑΣ",
    "ΜΕΛΙΤΗ": "ΚΥΤ ΜΕΛΙΤΗΣ",
    "ΑΜΥΝΤΑΙΟ": "ΚΥΤ ΑΜΥΝΤΑΙΟΥ",
    "ΚΑΣΣΑΝΔΡΙΑ": "ΚΑΣΣΑΝΔΡΕΙΑ",
    "ΝΕΑ ΕΛΒΕΤΙΑ": "Ν ΕΛΒΕΤΙΑ ΘΕΣΣΑΛΟΝΙΚΗ IV",
    "ΕΟΡΔΑΙΑ": "ΕΟΡΔΑΙΑ ΠΤΟΛΕΜΑΙΔΑ II",
    "ΘΗΣ ΚΟΜΟΤΗΝΗΣ": "Θ Η Σ ΚΟΜΟΤΗΝΗΣ",
    "ΓΙΑΝΝΙΤΣΑ": "ΓΙΑΝΝΙΤΣΑ Ν ΠΕΛΛΑ",
    "ΑΝΤΛΙΟΣΤΑΣΙΟ ΠΟΛΥΦΥΤΟΥ": "ΠΟΛΥΦΥΤΟΥ ΑΝΤΛΙΟΣΤΑΣΙΟ",
    "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ": "ΚΥΤ ΘΕΣΣΑΛΟΝΙΚΗΣ",
    "ΚΥΤ ΦΙΛΙΠΠΩΝ": "ΚΥΤ ΦΙΛΙΠΠΩΝ",
    "ΣΙΝΔΟΣ": "ΣΙΝΔΟΣ Β Π ΘΕΣΣΑΛΟΝΙΚΗΣ",
    "ΠΑΥΛΟΣ ΜΕΛΑΣ": "Π ΜΕΛΛΑΣ ΘΕΣΣΑΛ ΧΙ",
}


def normalize_text(value):
    text = str(value or "").replace("\x00", "").strip().upper()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("/", " ")
    text = re.sub(r"[().,\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_serial(value):
    serial = re.sub(r"[^A-Z0-9]", "", normalize_text(value))
    return serial.lstrip("0") or serial


def normalize_transformer_name(value):
    text = normalize_text(value)
    text = text.replace("Μ / Σ", "ΜΣ")
    text = text.replace("Μ Σ", "ΜΣ")
    text = text.replace("Μ/Σ", "ΜΣ")
    text = text.replace("ΜΕΤΑΣΧΗΜΑΤΙΣΤΗΣ", "ΜΣ")
    text = re.sub(r"^ΜΣ\s*", "ΜΣ", text)
    return text


def parse_asset_transformer_display(value):
    parts = [part.strip() for part in str(value or "").split(",")]
    if len(parts) < 3:
        return None, None
    return parts[0], parts[2]


def extract_breaker_code(value):
    raw = str(value or "").replace("\x00", "").strip().upper()
    raw = unicodedata.normalize("NFD", raw)
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    match = re.search(r"[ΡR]\s*-?\s*(\d+)", raw)
    if not match:
        return None
    return f"Ρ-{int(match.group(1))}"


def normalize_access_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.hour == 0 and value.minute == 0 and value.second == 0:
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M")
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
                return parsed.strftime("%Y-%m-%d")
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return text


def access_substation_key(value):
    base = normalize_text(value)
    return ACCESS_TO_SQLITE_SUBSTATION.get(base, base)


def person_key(value):
    text = normalize_text(value)
    parts = text.split()
    if not parts:
        return ""
    surname = parts[0]
    first_initial = parts[1][0] if len(parts) > 1 and parts[1] else ""
    return f"{surname}|{first_initial}"


def fuzzy_serial_match(left, right):
    if not left or not right:
        return False
    return left == right or left.endswith(right) or right.endswith(left)


def canonical_interconnection_gate(single_gate_number):
    mapping = {
        1: "ΠΥΛΗ 1-2",
        2: "ΠΥΛΗ 2-3",
        3: "ΠΥΛΗ 3-1",
    }
    return mapping.get(single_gate_number)


def build_access_connection():
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};" f"DBQ={ACCDB_PATH};"
    )
    return pyodbc.connect(conn_str)


def backup_sqlite_db():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"substations_before_access_updates_{timestamp}.db"
    shutil.copy2(SQLITE_PATH, backup_path)
    return backup_path


def load_access_substations(cursor):
    columns = [column.column_name for column in cursor.columns(table="tblSubstations")]
    rows = cursor.execute(
        f"SELECT [{columns[0]}], [{columns[1]}] FROM tblSubstations"
    ).fetchall()
    return {int(row[0]): row[1] for row in rows}


def load_access_models(cursor, table_name):
    rows = cursor.execute(f"SELECT * FROM [{table_name}]").fetchall()
    models = {}
    for row in rows:
        model_id = int(row[0])
        models[model_id] = {
            "manufacturer": row[1] if len(row) > 1 else None,
            "breaker_type": row[2] if len(row) > 2 else None,
        }
    return models


def load_access_maintainers(cursor):
    columns = [
        column.column_name for column in cursor.columns(table="tblMaintenancePersonnel")
    ]
    rows = cursor.execute(
        f"SELECT [{columns[0]}], [{columns[1]}] FROM tblMaintenancePersonnel"
    ).fetchall()
    return {int(row[0]): row[1] for row in rows}


def find_table_name(cursor, prefix, suffix):
    for row in cursor.tables(tableType="TABLE"):
        table_name = row.table_name
        if table_name.startswith(prefix) and table_name.endswith(suffix):
            return table_name
    raise RuntimeError(f"Could not find table matching {prefix}*{suffix}")


def load_access_hv_details(cursor, substations, models):
    rows = cursor.execute("SELECT * FROM tblHVCBDetails").fetchall()
    details = {}
    for row in rows:
        detail_id = int(row[0])
        substation_id = int(row[1]) if row[1] is not None else None
        model_id = int(row[2]) if row[2] is not None else None
        model = models.get(model_id, {})
        details[detail_id] = {
            "access_substation_name": substations.get(substation_id),
            "access_breaker_name": row[3],
            "access_serial": row[4],
            "access_manufacture_year": row[5],
            "access_model_id": model_id,
            "access_manufacturer": model.get("manufacturer"),
            "access_breaker_type": model.get("breaker_type"),
        }
    return details


def load_access_mv_details(cursor, substations, models):
    rows = cursor.execute("SELECT * FROM tblMVCBDetails").fetchall()
    details = {}
    for row in rows:
        detail_id = int(row[0])
        substation_id = int(row[1]) if row[1] is not None else None
        model_id = int(row[2]) if row[2] is not None else None
        model = models.get(model_id, {})
        details[detail_id] = {
            "access_substation_name": substations.get(substation_id),
            "access_breaker_name": row[3],
            "access_serial": row[4],
            "access_manufacture_year": row[5],
            "access_model_id": model_id,
            "access_manufacturer": model.get("manufacturer"),
            "access_breaker_type": model.get("breaker_type"),
        }
    return details


def load_access_transformers(cursor):
    transformers = {}
    rows = cursor.execute("SELECT * FROM tblPowerTransformers").fetchall()
    for row in rows:
        transformer_id = int(row[0])
        transformers[transformer_id] = {
            "transformer_id": transformer_id,
            "substation_name": row[1],
            "transformer_name": row[2],
            "serial_no": row[4],
            "manufacture_year": row[6],
            "transformer_type": row[5],
        }

    try:
        rows = cursor.execute(
            "SELECT [HVMVTransformer ID], [Ονομασία], [Serial No] FROM qryPowerTransformersActive"
        ).fetchall()
        for row in rows:
            transformer_id = int(row[0])
            item = transformers.setdefault(
                transformer_id,
                {
                    "transformer_id": transformer_id,
                    "substation_name": None,
                    "transformer_name": None,
                    "serial_no": None,
                    "manufacture_year": None,
                    "transformer_type": None,
                },
            )
            if not item.get("transformer_name") and row[1]:
                item["transformer_name"] = row[1]
            if not item.get("serial_no") and row[2]:
                item["serial_no"] = row[2]
    except Exception:
        pass

    try:
        rows = cursor.execute(
            "SELECT DISTINCT [HVMVTransformer ID], [Transformer] FROM qryAssetTransformer"
        ).fetchall()
        for row in rows:
            transformer_id = int(row[0])
            substation_name, transformer_name = parse_asset_transformer_display(row[1])
            item = transformers.setdefault(
                transformer_id,
                {
                    "transformer_id": transformer_id,
                    "substation_name": None,
                    "transformer_name": None,
                    "serial_no": None,
                    "manufacture_year": None,
                    "transformer_type": None,
                },
            )
            if not item.get("substation_name") and substation_name:
                item["substation_name"] = substation_name
            if not item.get("transformer_name") and transformer_name:
                item["transformer_name"] = transformer_name
    except Exception:
        pass

    return transformers


def load_sqlite_hv_breakers(conn):
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.id AS element_id,
            e.name AS element_name,
            e.serial_number,
            e.substation_id,
            s.name AS substation_name,
            e.manufacturer,
            e.element_type,
            e.gate,
            e.manufacture_year
        FROM elements e
        JOIN substations s ON s.id = e.substation_id
        WHERE e.element_type = 'Διακόπτης ΥΤ'
        ORDER BY s.name, e.name
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["norm_substation"] = normalize_text(item["substation_name"])
        item["norm_serial"] = normalize_serial(item["serial_number"])
        item["breaker_code"] = extract_breaker_code(item["element_name"])
        result.append(item)
    return result


def load_sqlite_mv_breakers(conn):
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.id AS element_id,
            e.name AS element_name,
            e.serial_number,
            e.substation_id,
            s.name AS substation_name,
            e.manufacturer,
            e.element_type,
            e.gate,
            e.is_main_switch,
            e.manufacture_year
        FROM elements e
        JOIN substations s ON s.id = e.substation_id
        WHERE e.element_type = 'Διακόπτης ΜΤ'
        ORDER BY s.name, e.name
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["norm_substation"] = normalize_text(item["substation_name"])
        item["norm_serial"] = normalize_serial(item["serial_number"])
        item["norm_manufacturer"] = normalize_text(item["manufacturer"])
        item["breaker_code"] = extract_breaker_code(item["element_name"])
        result.append(item)
    return result


def load_sqlite_transformers(conn):
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.id AS element_id,
            e.name AS element_name,
            e.serial_number,
            e.substation_id,
            s.name AS substation_name,
            e.gate,
            e.manufacture_year
        FROM elements e
        JOIN substations s ON s.id = e.substation_id
        WHERE e.element_type LIKE '%Μετασχηματιστ%'
           OR e.element_type LIKE '%transformer%'
           OR e.name LIKE 'ΜΣ%'
        ORDER BY s.name, e.name
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["norm_substation"] = normalize_text(item["substation_name"])
        item["norm_serial"] = normalize_serial(item["serial_number"])
        item["norm_name"] = normalize_transformer_name(item["element_name"])
        result.append(item)
    return result


def load_sqlite_people(conn):
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, name FROM people").fetchall()
    people = {}
    for row in rows:
        item = dict(row)
        people.setdefault(person_key(item["name"]), []).append(item)
    return people


def find_matching_hv_element(access_row, sqlite_breakers):
    access_substation = access_substation_key(access_row.get("access_substation_name"))
    access_serial = normalize_serial(access_row.get("access_serial"))
    access_code = extract_breaker_code(access_row.get("access_breaker_name"))

    serial_candidates = []
    if access_serial:
        serial_candidates = [
            row for row in sqlite_breakers if row["norm_serial"] == access_serial
        ]
        if len(serial_candidates) == 1:
            return serial_candidates[0], "serial"

    compatible_substations = []
    if access_substation:
        compatible_substations = [
            row
            for row in sqlite_breakers
            if row["norm_substation"] == access_substation
        ]
        if not compatible_substations:
            compatible_substations = [
                row
                for row in sqlite_breakers
                if access_substation in row["norm_substation"]
                or row["norm_substation"] in access_substation
            ]

    if compatible_substations and access_code:
        exact_code_matches = [
            row
            for row in compatible_substations
            if row["breaker_code"] == access_code and row["element_name"] == access_code
        ]
        if len(exact_code_matches) == 1:
            return exact_code_matches[0], "substation+exact_code"

        code_matches = [
            row for row in compatible_substations if row["breaker_code"] == access_code
        ]
        if len(code_matches) == 1:
            return code_matches[0], "substation+code"

    if len(serial_candidates) == 1:
        return serial_candidates[0], "serial"

    return None, None


def find_matching_mv_element(access_row, sqlite_breakers):
    access_substation = access_substation_key(access_row.get("access_substation_name"))
    access_serial = normalize_serial(access_row.get("access_serial"))
    access_code = extract_breaker_code(access_row.get("access_breaker_name"))
    access_manufacturer = normalize_text(access_row.get("access_manufacturer"))

    if access_serial:
        serial_candidates = [
            row for row in sqlite_breakers if row["norm_serial"] == access_serial
        ]
        if len(serial_candidates) == 1:
            return serial_candidates[0], "serial"

    compatible_substations = []
    if access_substation:
        compatible_substations = [
            row
            for row in sqlite_breakers
            if row["norm_substation"] == access_substation
        ]
        if not compatible_substations:
            fuzzy_substations = [
                row
                for row in sqlite_breakers
                if access_substation in row["norm_substation"]
                or row["norm_substation"] in access_substation
            ]
            if len({row["norm_substation"] for row in fuzzy_substations}) == 1:
                compatible_substations = fuzzy_substations

    if compatible_substations and access_serial:
        fuzzy_serial_matches = [
            row
            for row in compatible_substations
            if fuzzy_serial_match(access_serial, row["norm_serial"])
        ]
        if len(fuzzy_serial_matches) == 1:
            return fuzzy_serial_matches[0], "substation+fuzzy_serial"

    if compatible_substations and access_code:
        exact_code_matches = [
            row
            for row in compatible_substations
            if row["breaker_code"] == access_code and row["element_name"] == access_code
        ]
        if len(exact_code_matches) == 1:
            return exact_code_matches[0], "substation+exact_code"

        code_matches = [
            row for row in compatible_substations if row["breaker_code"] == access_code
        ]
        if len(code_matches) > 1 and access_manufacturer:
            manufacturer_matches = [
                row
                for row in code_matches
                if row["norm_manufacturer"] == access_manufacturer
            ]
            if len(manufacturer_matches) == 1:
                return manufacturer_matches[0], "substation+code+manufacturer"
        if len(code_matches) == 1:
            return code_matches[0], "substation+code"

    return None, None


def find_matching_transformer(access_row, sqlite_transformers):
    access_serial = normalize_serial(access_row.get("serial_no"))
    access_substation = access_substation_key(access_row.get("substation_name"))
    access_name = normalize_transformer_name(access_row.get("transformer_name"))

    serial_candidates = []
    if access_serial:
        serial_candidates = [
            row for row in sqlite_transformers if row["norm_serial"] == access_serial
        ]
        if len(serial_candidates) == 1:
            return serial_candidates[0], "serial"

    compatible_substations = []
    if access_substation:
        compatible_substations = [
            row
            for row in sqlite_transformers
            if row["norm_substation"] == access_substation
        ]
        if not compatible_substations:
            compatible_substations = [
                row
                for row in sqlite_transformers
                if access_substation in row["norm_substation"]
                or row["norm_substation"] in access_substation
            ]

    if compatible_substations and access_name:
        name_matches = [
            row for row in compatible_substations if row["norm_name"] == access_name
        ]
        if len(name_matches) == 1:
            return name_matches[0], "substation+name"

    if compatible_substations and access_serial:
        serial_matches = [
            row for row in compatible_substations if row["norm_serial"] == access_serial
        ]
        if len(serial_matches) == 1:
            return serial_matches[0], "substation+serial"

    return None, None


def map_responsible_id(access_name, sqlite_people):
    if not access_name:
        return None
    matches = sqlite_people.get(person_key(access_name), [])
    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        return matches[0]["id"]
    return None


def find_existing_maintenance(conn, element_id, date_value):
    row = conn.execute(
        """
        SELECT m.id
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        WHERE me.element_id = ?
          AND date(m.date_time) = date(?)
        ORDER BY m.id
        LIMIT 1
        """,
        (element_id, date_value),
    ).fetchone()
    return row[0] if row else None


def ensure_maintenance_element(conn, maintenance_id, element_id, element_comments=None):
    existing = conn.execute(
        "SELECT id FROM maintenance_elements WHERE maintenance_id = ? AND element_id = ?",
        (maintenance_id, element_id),
    ).fetchone()
    if existing:
        if element_comments:
            conn.execute(
                """
                UPDATE maintenance_elements
                SET element_comments = CASE
                    WHEN COALESCE(TRIM(element_comments), '') = '' THEN ?
                    ELSE element_comments
                END
                WHERE maintenance_id = ? AND element_id = ?
                """,
                (element_comments, maintenance_id, element_id),
            )
        return
    conn.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
        (maintenance_id, element_id, element_comments),
    )


def upsert_pending_tasks(conn, maintenance_id, description):
    text = (description or "").strip()
    existing = conn.execute(
        "SELECT tasks_text FROM maintenance_pending_tasks WHERE maintenance_id = ?",
        (maintenance_id,),
    ).fetchone()
    if existing and existing[0]:
        existing_text = existing[0].strip()
        if text and text not in existing_text:
            merged = f"{existing_text}\n\n{text}"
        else:
            merged = existing_text
    else:
        merged = text
    conn.execute(
        "INSERT OR REPLACE INTO maintenance_pending_tasks (maintenance_id, tasks_text, created_at) VALUES (?, ?, datetime('now'))",
        (maintenance_id, merged),
    )


def next_maintenance_id(conn):
    maintenance_max = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM maintenance"
    ).fetchone()[0]
    link_max = conn.execute(
        "SELECT COALESCE(MAX(maintenance_id), 0) FROM maintenance_elements"
    ).fetchone()[0]
    return max(maintenance_max, link_max) + 1


def sync_maintenance_people(conn, maintenance_id, responsible_id, description):
    if responsible_id is None and not description:
        return
    conn.execute(
        "DELETE FROM maintenance_people WHERE maintenance_id = ?", (maintenance_id,)
    )
    if responsible_id:
        conn.execute(
            "INSERT INTO maintenance_people (maintenance_id, person_id, role) VALUES (?, ?, 'responsible')",
            (maintenance_id, responsible_id),
        )
    crew_ids = sorted(
        _find_people_in_body(
            conn,
            description or "",
            exclude_ids={responsible_id} if responsible_id else set(),
        )
    )
    for person_id in crew_ids:
        conn.execute(
            "INSERT INTO maintenance_people (maintenance_id, person_id, role) VALUES (?, ?, 'crew')",
            (maintenance_id, person_id),
        )


def sync_element_maintenance_date(conn, element_id):
    latest = conn.execute(
        """
        SELECT MAX(m.date_time)
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        WHERE me.element_id = ?
        """,
        (element_id,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE elements SET maintenance_date = ? WHERE id = ?", (latest, element_id)
    )


def sync_substation_last_maintenance(conn, substation_id):
    latest = conn.execute(
        "SELECT MAX(date_time) FROM maintenance WHERE substation_id = ?",
        (substation_id,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE substations SET last_maintenance = ? WHERE id = ?",
        (latest, substation_id),
    )


def create_or_get_maintenance(
    conn,
    current_maintenance_id,
    element,
    date_value,
    description,
    responsible_id,
):
    maintenance_id = find_existing_maintenance(conn, element["element_id"], date_value)
    created = False
    if maintenance_id is None:
        maintenance_id = current_maintenance_id
        conn.execute(
            """
            INSERT INTO maintenance (
                id, substation_id, name, date_time, overall_comments, responsible_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                maintenance_id,
                element["substation_id"],
                None,
                date_value,
                description or None,
                responsible_id,
            ),
        )
        created = True
    else:
        conn.execute(
            """
            UPDATE maintenance
            SET overall_comments = CASE
                    WHEN COALESCE(TRIM(overall_comments), '') = '' THEN COALESCE(?, overall_comments)
                    ELSE overall_comments
                END,
                responsible_id = COALESCE(responsible_id, ?)
            WHERE id = ?
            """,
            (description or None, responsible_id, maintenance_id),
        )
    ensure_maintenance_element(conn, maintenance_id, element["element_id"], description)
    sync_maintenance_people(conn, maintenance_id, responsible_id, description)
    return maintenance_id, created


def update_manufacture_years(
    conn, access_hv, access_mv, access_tx, sqlite_hv, sqlite_mv, sqlite_tx, report
):
    for access_row in access_hv.values():
        if not access_row.get("access_manufacture_year"):
            continue
        element, match_method = find_matching_hv_element(access_row, sqlite_hv)
        if not element:
            report["manufacture_unmatched_hv"] += 1
            continue
        if not str(element.get("manufacture_year") or "").strip():
            conn.execute(
                "UPDATE elements SET manufacture_year = ? WHERE id = ?",
                (
                    str(access_row["access_manufacture_year"]).strip(),
                    element["element_id"],
                ),
            )
            report["manufacture_updated_hv"] += 1
            report[f"manufacture_match_{match_method}"] += 1

    for access_row in access_mv.values():
        if not access_row.get("access_manufacture_year"):
            continue
        element, match_method = find_matching_mv_element(access_row, sqlite_mv)
        if not element:
            report["manufacture_unmatched_mv"] += 1
            continue
        if not str(element.get("manufacture_year") or "").strip():
            conn.execute(
                "UPDATE elements SET manufacture_year = ? WHERE id = ?",
                (
                    str(access_row["access_manufacture_year"]).strip(),
                    element["element_id"],
                ),
            )
            report["manufacture_updated_mv"] += 1
            report[f"manufacture_match_{match_method}"] += 1

    for access_row in access_tx.values():
        if not access_row.get("manufacture_year"):
            continue
        element, match_method = find_matching_transformer(access_row, sqlite_tx)
        if not element:
            report["manufacture_unmatched_transformer"] += 1
            continue
        if not str(element.get("manufacture_year") or "").strip():
            conn.execute(
                "UPDATE elements SET manufacture_year = ? WHERE id = ?",
                (str(access_row["manufacture_year"]).strip(), element["element_id"]),
            )
            report["manufacture_updated_transformer"] += 1
            report[f"manufacture_match_{match_method}"] += 1


def update_gates(
    conn,
    gate_maps,
    access_hv,
    access_mv,
    access_tx,
    sqlite_hv,
    sqlite_mv,
    sqlite_tx,
    report,
):
    hv_targets = {}
    hv_candidates = {}
    for access_row in access_hv.values():
        element, _ = find_matching_hv_element(access_row, sqlite_hv)
        if not element:
            continue
        gate_number = find_hv_gate(
            gate_maps,
            access_row.get("access_substation_name"),
            access_row.get("access_breaker_name"),
            access_row.get("access_serial"),
        )
        desired_gate = (
            format_gate_label(gate_number) if gate_number is not None else None
        )
        if desired_gate:
            hv_targets.setdefault(element["element_id"], element)
            hv_candidates.setdefault(element["element_id"], set()).add(desired_gate)
    for element_id, desireds in hv_candidates.items():
        if len(desireds) != 1:
            report["gates_conflicted_hv"] += 1
            continue
        element = hv_targets[element_id]
        desired_gate = next(iter(desireds))
        if desired_gate != (element.get("gate") or ""):
            conn.execute(
                "UPDATE elements SET gate = ? WHERE id = ?", (desired_gate, element_id)
            )
            report["gates_updated_hv"] += 1

    mv_targets = {}
    mv_candidates = {}
    for access_row in access_mv.values():
        element, _ = find_matching_mv_element(access_row, sqlite_mv)
        if not element:
            continue
        gate_number = find_mv_gate(
            gate_maps,
            access_row.get("access_substation_name"),
            access_row.get("access_breaker_name"),
            access_row.get("access_serial"),
        )
        if gate_number is None:
            continue
        desired_gate = (
            canonical_interconnection_gate(gate_number)
            if element.get("is_main_switch") == 2
            else format_gate_label(gate_number)
        )
        if desired_gate:
            mv_targets.setdefault(element["element_id"], element)
            mv_candidates.setdefault(element["element_id"], set()).add(desired_gate)
    for element_id, desireds in mv_candidates.items():
        if len(desireds) != 1:
            report["gates_conflicted_mv"] += 1
            continue
        element = mv_targets[element_id]
        desired_gate = next(iter(desireds))
        if desired_gate != (element.get("gate") or ""):
            conn.execute(
                "UPDATE elements SET gate = ? WHERE id = ?", (desired_gate, element_id)
            )
            report["gates_updated_mv"] += 1

    tx_targets = {}
    tx_candidates = {}
    for access_row in access_tx.values():
        element, _ = find_matching_transformer(access_row, sqlite_tx)
        if not element:
            continue
        gate_number = find_transformer_gate(
            gate_maps,
            access_row.get("substation_name"),
            access_row.get("transformer_name"),
            access_row.get("serial_no"),
        )
        desired_gate = (
            format_gate_label(gate_number) if gate_number is not None else None
        )
        if desired_gate:
            tx_targets.setdefault(element["element_id"], element)
            tx_candidates.setdefault(element["element_id"], set()).add(desired_gate)
    for element_id, desireds in tx_candidates.items():
        if len(desireds) != 1:
            report["gates_conflicted_transformer"] += 1
            continue
        element = tx_targets[element_id]
        desired_gate = next(iter(desireds))
        if desired_gate != (element.get("gate") or ""):
            conn.execute(
                "UPDATE elements SET gate = ? WHERE id = ?", (desired_gate, element_id)
            )
            report["gates_updated_transformer"] += 1


def import_sf6_leakages(
    conn,
    cursor,
    access_hv,
    access_mv,
    sqlite_hv,
    sqlite_mv,
    sqlite_people,
    maintainers,
    report,
):
    current_maintenance_id = next_maintenance_id(conn)
    touched_elements = set()
    touched_substations = set()

    leak_specs = [
        ("tblHVCBLeakSF6", access_hv, sqlite_hv, find_matching_hv_element, "hv"),
        ("tblMVCBLeakSF6", access_mv, sqlite_mv, find_matching_mv_element, "mv"),
    ]

    for table_name, access_details, sqlite_rows, matcher, label in leak_specs:
        rows = cursor.execute(f"SELECT * FROM [{table_name}]").fetchall()
        for row in rows:
            date_value = normalize_access_datetime(row[1])
            access_equipment_id = int(row[2]) if row[2] is not None else None
            quantity_grams = row[3]
            responsible_fk = int(row[4]) if row[4] is not None else None

            access_row = access_details.get(access_equipment_id)
            if not access_row:
                report[f"sf6_unmatched_access_{label}"] += 1
                continue

            element, match_method = matcher(access_row, sqlite_rows)
            if not element:
                report[f"sf6_unmatched_sqlite_{label}"] += 1
                continue

            try:
                sf6_leakage_kg = float(quantity_grams) / 1000.0
            except (TypeError, ValueError):
                report["sf6_quantity_parse_errors"] += 1
                continue

            responsible_id = map_responsible_id(
                maintainers.get(responsible_fk), sqlite_people
            )
            description = f"SF6 leakage imported from Access {table_name}"
            maintenance_id, created = create_or_get_maintenance(
                conn,
                current_maintenance_id,
                element,
                date_value,
                description,
                responsible_id,
            )
            if created:
                current_maintenance_id += 1
                report["sf6_created_maintenance"] += 1
            conn.execute(
                """
                UPDATE maintenance_elements
                SET sf6_leakage_kg = ?,
                    sf6_leak_methodology = ?
                WHERE maintenance_id = ? AND element_id = ?
                """,
                (
                    sf6_leakage_kg,
                    "Πλήρωση",
                    maintenance_id,
                    element["element_id"],
                ),
            )
            report["sf6_updated"] += 1
            report[f"sf6_match_{match_method}"] += 1
            touched_elements.add(element["element_id"])
            touched_substations.add(element["substation_id"])

    for element_id in touched_elements:
        sync_element_maintenance_date(conn, element_id)
    for substation_id in touched_substations:
        sync_substation_last_maintenance(conn, substation_id)

    return current_maintenance_id


def import_incomplete_maintenances(
    conn,
    cursor,
    access_hv,
    access_mv,
    access_tx,
    sqlite_hv,
    sqlite_mv,
    sqlite_tx,
    sqlite_people,
    maintainers,
    current_maintenance_id,
    report,
):
    mv_table = find_table_name(cursor, "tblMVC", "MaintenanceData")
    table_specs = [
        (
            "tblHVCBMaintenanceData",
            access_hv,
            sqlite_hv,
            find_matching_hv_element,
            "breaker_fk",
            "hv",
        ),
        (mv_table, access_mv, sqlite_mv, find_matching_mv_element, "breaker_fk", "mv"),
        (
            "tblPowerTransMaintenanceData",
            access_tx,
            sqlite_tx,
            find_matching_transformer,
            "transformer_fk",
            "transformer",
        ),
    ]

    touched_elements = set()
    touched_substations = set()

    for table_name, access_details, sqlite_rows, matcher, _, label in table_specs:
        rows = cursor.execute(f"SELECT * FROM [{table_name}]").fetchall()
        for row in rows:
            completed = bool(row[5]) if row[5] is not None else None
            if completed is not False:
                continue
            access_equipment_id = int(row[2]) if row[2] is not None else None
            access_row = access_details.get(access_equipment_id)
            if not access_row:
                report[f"incomplete_unmatched_access_{label}"] += 1
                continue

            element, match_method = matcher(access_row, sqlite_rows)
            if not element:
                report[f"incomplete_unmatched_sqlite_{label}"] += 1
                continue

            date_value = normalize_access_datetime(row[1])
            description = row[4] or ""
            responsible_fk = int(row[3]) if row[3] is not None else None
            responsible_id = map_responsible_id(
                maintainers.get(responsible_fk), sqlite_people
            )
            maintenance_id, created = create_or_get_maintenance(
                conn,
                current_maintenance_id,
                element,
                date_value,
                description,
                responsible_id,
            )
            if created:
                current_maintenance_id += 1
                report["incomplete_created_maintenance"] += 1
            upsert_pending_tasks(conn, maintenance_id, description)
            report["incomplete_marked"] += 1
            report[f"incomplete_match_{match_method}"] += 1
            touched_elements.add(element["element_id"])
            touched_substations.add(element["substation_id"])

    for element_id in touched_elements:
        sync_element_maintenance_date(conn, element_id)
    for substation_id in touched_substations:
        sync_substation_last_maintenance(conn, substation_id)

    return current_maintenance_id


def main():
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_sqlite_db()
    report = Counter()
    report["backup_path"] = str(backup_path)

    gate_maps = build_access_asset_gate_maps(ACCDB_PATH)

    with sqlite3.connect(SQLITE_PATH) as conn:
        sqlite_people = load_sqlite_people(conn)
        sqlite_hv = load_sqlite_hv_breakers(conn)
        sqlite_mv = load_sqlite_mv_breakers(conn)
        sqlite_tx = load_sqlite_transformers(conn)

        with build_access_connection() as access_conn:
            cursor = access_conn.cursor()
            substations = load_access_substations(cursor)
            maintainers = load_access_maintainers(cursor)
            hv_models = load_access_models(cursor, "tblHVCBModel")
            mv_models = load_access_models(cursor, "tblMVCBModel")
            access_hv = load_access_hv_details(cursor, substations, hv_models)
            access_mv = load_access_mv_details(cursor, substations, mv_models)
            access_tx = load_access_transformers(cursor)

            update_manufacture_years(
                conn,
                access_hv,
                access_mv,
                access_tx,
                sqlite_hv,
                sqlite_mv,
                sqlite_tx,
                report,
            )
            update_gates(
                conn,
                gate_maps,
                access_hv,
                access_mv,
                access_tx,
                sqlite_hv,
                sqlite_mv,
                sqlite_tx,
                report,
            )
            current_maintenance_id = import_sf6_leakages(
                conn,
                cursor,
                access_hv,
                access_mv,
                sqlite_hv,
                sqlite_mv,
                sqlite_people,
                maintainers,
                report,
            )
            import_incomplete_maintenances(
                conn,
                cursor,
                access_hv,
                access_mv,
                access_tx,
                sqlite_hv,
                sqlite_mv,
                sqlite_tx,
                sqlite_people,
                maintainers,
                current_maintenance_id,
                report,
            )

        conn.commit()

    report_data = dict(report)
    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report_data, handle, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "backup_path": report_data["backup_path"],
                "manufacture_updates": report_data.get("manufacture_updated_hv", 0)
                + report_data.get("manufacture_updated_mv", 0)
                + report_data.get("manufacture_updated_transformer", 0),
                "gate_updates": report_data.get("gates_updated_hv", 0)
                + report_data.get("gates_updated_mv", 0)
                + report_data.get("gates_updated_transformer", 0),
                "sf6_updates": report_data.get("sf6_updated", 0),
                "incomplete_marked": report_data.get("incomplete_marked", 0),
                "report_path": str(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
