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

from maintenance_email_importer import _find_people_in_body
from access_gate_utils import (
    build_access_asset_gate_maps,
    find_hv_gate,
    format_gate_label,
)


ACCDB_PATH = Path(
    r"C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations\substation_asset_maintenance.accdb"
)
SQLITE_PATH = Path(
    r"C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations\substations.db"
)
REPORT_PATH = SQLITE_PATH.parent / "reports" / "hvcb_access_import_report.json"
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
    text = str(value or "").strip().upper()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("/", " ")
    text = re.sub(r"[().,\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_serial(value):
    serial = re.sub(r"[^A-Z0-9]", "", normalize_text(value))
    return serial.lstrip("0") or serial


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


def extract_breaker_code(value):
    raw = str(value or "").strip().upper()
    raw = unicodedata.normalize("NFD", raw)
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    match = re.search(r"[ΡR]\s*-?\s*(\d+)", raw)
    if not match:
        return None
    return f"Ρ-{int(match.group(1))}"


def build_access_connection():
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={ACCDB_PATH};"
    )
    return pyodbc.connect(conn_str)


def get_access_columns(cursor, table_name):
    return [column.column_name for column in cursor.columns(table=table_name)]


def load_access_substations(cursor):
    columns = get_access_columns(cursor, "tblSubstations")
    rows = cursor.execute(
        f"SELECT [{columns[0]}], [{columns[1]}] FROM tblSubstations"
    ).fetchall()
    return {int(row[0]): row[1] for row in rows}


def load_access_models(cursor):
    columns = get_access_columns(cursor, "tblHVCBModel")
    rows = cursor.execute(
        f"SELECT [{columns[0]}], [{columns[1]}], [{columns[2]}] FROM tblHVCBModel"
    ).fetchall()
    models = {}
    for row in rows:
        models[int(row[0])] = {
            "manufacturer": row[1],
            "breaker_type": row[2],
        }
    return models


def load_access_maintainers(cursor):
    columns = get_access_columns(cursor, "tblMaintenancePersonnel")
    rows = cursor.execute(
        f"SELECT [{columns[0]}], [{columns[1]}] FROM tblMaintenancePersonnel"
    ).fetchall()
    return {int(row[0]): row[1] for row in rows}


def load_access_breaker_details(cursor, substations, models):
    columns = get_access_columns(cursor, "tblHVCBDetails")
    rows = cursor.execute(
        f"SELECT [{columns[0]}], [{columns[1]}], [{columns[2]}], [{columns[3]}], [{columns[4]}], [{columns[9]}] FROM tblHVCBDetails"
    ).fetchall()

    details = {}
    for row in rows:
        breaker_id = int(row[0])
        substation_id = int(row[1]) if row[1] is not None else None
        model_id = int(row[2]) if row[2] is not None else None
        model = models.get(model_id, {})
        details[breaker_id] = {
            "breaker_fk": breaker_id,
            "access_substation_name": substations.get(substation_id),
            "access_breaker_name": row[3],
            "access_serial": row[4],
            "access_active": bool(row[5]) if row[5] is not None else None,
            "access_model_id": model_id,
            "access_manufacturer": model.get("manufacturer"),
            "access_breaker_type": model.get("breaker_type"),
        }
    return details


def load_access_maintenance_rows():
    with build_access_connection() as conn:
        cursor = conn.cursor()
        substations = load_access_substations(cursor)
        models = load_access_models(cursor)
        maintainers = load_access_maintainers(cursor)
        details = load_access_breaker_details(cursor, substations, models)

        columns = get_access_columns(cursor, "tblHVCBMaintenanceData")
        rows = cursor.execute(
            f"SELECT [{columns[0]}], [{columns[1]}], [{columns[2]}], [{columns[3]}], [{columns[4]}], [{columns[5]}] "
            f"FROM tblHVCBMaintenanceData ORDER BY [{columns[0]}]"
        ).fetchall()

    maintenance_rows = []
    for row in rows:
        breaker_fk = int(row[2]) if row[2] is not None else None
        detail = details.get(breaker_fk)
        maintenance_rows.append(
            {
                "maintenance_id": int(row[0]),
                "date": normalize_access_datetime(row[1]),
                "breaker_fk": breaker_fk,
                "maintainer_fk": int(row[3]) if row[3] is not None else None,
                "description": row[4] or "",
                "completed": bool(row[5]) if row[5] is not None else None,
                "access_maintainer_name": maintainers.get(int(row[3]))
                if row[3] is not None
                else None,
                **(detail or {}),
            }
        )
    return maintenance_rows


def load_sqlite_breakers(conn):
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
            e.type,
            e.element_type,
            e.gate
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


def load_sqlite_people(conn):
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, name FROM people").fetchall()
    people = {}
    for row in rows:
        item = dict(row)
        people.setdefault(person_key(item["name"]), []).append(item)
    return people


def backup_sqlite_db():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"substations_before_access_hvcb_import_{timestamp}.db"
    shutil.copy2(SQLITE_PATH, backup_path)
    return backup_path


def find_matching_element(maintenance_row, sqlite_breakers):
    access_substation = access_substation_key(
        maintenance_row.get("access_substation_name")
    )
    access_serial = normalize_serial(maintenance_row.get("access_serial"))
    access_code = extract_breaker_code(maintenance_row.get("access_breaker_name"))

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


def map_responsible_id(access_name, sqlite_people):
    if not access_name:
        return None, "missing_access_person"
    key = person_key(access_name)
    matches = sqlite_people.get(key, [])
    if len(matches) == 1:
        return matches[0]["id"], "person_key"
    if len(matches) > 1:
        return matches[0]["id"], "person_key_ambiguous"
    return None, "person_not_found"


def maintenance_exists(
    conn, substation_id, element_id, element_name, date_value, description
):
    row = conn.execute(
        """
        SELECT m.id
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        WHERE m.substation_id = ?
          AND me.element_id = ?
          AND date(m.date_time) = date(?)
          AND COALESCE(m.overall_comments, '') = COALESCE(?, '')
          AND COALESCE(me.element_comments, '') = COALESCE(?, '')
        LIMIT 1
        """,
        (substation_id, element_id, date_value, description, description),
    ).fetchone()
    return row[0] if row else None


def sync_maintenance_people(conn, maintenance_id, responsible_id, description):
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
    return crew_ids


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


def update_element_gate_from_access(conn, element, maintenance_row, gate_maps):
    gate_number = find_hv_gate(
        gate_maps,
        maintenance_row.get("access_substation_name"),
        maintenance_row.get("access_breaker_name"),
        maintenance_row.get("access_serial"),
    )
    if gate_number is None:
        return False
    desired_gate = format_gate_label(gate_number)
    if desired_gate and desired_gate != element.get("gate"):
        conn.execute(
            "UPDATE elements SET gate = ? WHERE id = ?",
            (desired_gate, element["element_id"]),
        )
        element["gate"] = desired_gate
        return True
    return False


def next_maintenance_id(conn):
    maintenance_max = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM maintenance"
    ).fetchone()[0]
    link_max = conn.execute(
        "SELECT COALESCE(MAX(maintenance_id), 0) FROM maintenance_elements"
    ).fetchone()[0]
    return max(maintenance_max, link_max) + 1


def main():
    access_maintenance = load_access_maintenance_rows()
    gate_maps = build_access_asset_gate_maps(ACCDB_PATH)

    backup_path = backup_sqlite_db()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "backup_path": str(backup_path),
        "maintenance_total": len(access_maintenance),
        "inserted": 0,
        "skipped_existing": 0,
        "unmatched": [],
        "unmatched_reasons": Counter(),
        "responsible_mappings": Counter(),
        "match_methods": Counter(),
    }

    with sqlite3.connect(SQLITE_PATH) as conn:
        sqlite_breakers = load_sqlite_breakers(conn)
        sqlite_people = load_sqlite_people(conn)
        current_maintenance_id = next_maintenance_id(conn)

        for row in access_maintenance:
            if not row.get("date"):
                report["unmatched_reasons"]["missing_maintenance_date"] += 1
                report["unmatched"].append(
                    {
                        "maintenance_id": row["maintenance_id"],
                        "reason": "missing_maintenance_date",
                        "breaker_fk": row.get("breaker_fk"),
                    }
                )
                continue

            if not row.get("breaker_fk"):
                report["unmatched_reasons"]["missing_access_breaker_lookup"] += 1
                report["unmatched"].append(
                    {
                        "maintenance_id": row["maintenance_id"],
                        "reason": "missing_access_breaker_lookup",
                    }
                )
                continue

            element, match_method = find_matching_element(row, sqlite_breakers)
            if not element:
                report["unmatched_reasons"]["sqlite_breaker_not_found"] += 1
                report["unmatched"].append(
                    {
                        "maintenance_id": row["maintenance_id"],
                        "reason": "sqlite_breaker_not_found",
                        "breaker_fk": row.get("breaker_fk"),
                        "access_substation": row.get("access_substation_name"),
                        "access_breaker_name": row.get("access_breaker_name"),
                        "access_serial": row.get("access_serial"),
                        "access_manufacturer": row.get("access_manufacturer"),
                        "access_breaker_type": row.get("access_breaker_type"),
                    }
                )
                continue

            report["match_methods"][match_method] += 1

            responsible_id, mapping_method = map_responsible_id(
                row.get("access_maintainer_name"), sqlite_people
            )
            report["responsible_mappings"][mapping_method] += 1

            existing_id = maintenance_exists(
                conn,
                element["substation_id"],
                element["element_id"],
                element["element_name"],
                row["date"],
                row["description"],
            )
            if existing_id:
                report["skipped_existing"] += 1
                continue

            update_element_gate_from_access(conn, element, row, gate_maps)

            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO maintenance (id, substation_id, name, date_time, overall_comments, responsible_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    current_maintenance_id,
                    element["substation_id"],
                    None,
                    row["date"],
                    row["description"],
                    responsible_id,
                ),
            )
            maintenance_id = current_maintenance_id
            current_maintenance_id += 1

            cursor.execute(
                """
                INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments)
                VALUES (?, ?, ?)
                """,
                (maintenance_id, element["element_id"], row["description"]),
            )
            sync_maintenance_people(
                conn, maintenance_id, responsible_id, row["description"]
            )
            sync_element_maintenance_date(conn, element["element_id"])
            sync_substation_last_maintenance(conn, element["substation_id"])
            report["inserted"] += 1

        conn.commit()

    report["unmatched_reasons"] = dict(report["unmatched_reasons"])
    report["responsible_mappings"] = dict(report["responsible_mappings"])
    report["match_methods"] = dict(report["match_methods"])
    report["unmatched_preview"] = report["unmatched"][:50]

    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "backup_path": report["backup_path"],
                "maintenance_total": report["maintenance_total"],
                "inserted": report["inserted"],
                "skipped_existing": report["skipped_existing"],
                "unmatched_count": len(report["unmatched"]),
                "unmatched_reasons": report["unmatched_reasons"],
                "responsible_mappings": report["responsible_mappings"],
                "match_methods": report["match_methods"],
                "report_path": str(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
