import json
import re
import shutil
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

import pyodbc


ACCDB_PATH = Path(
    r"C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations\substation_asset_maintenance.accdb"
)
SQLITE_PATH = Path(
    r"C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations\substations.db"
)
REPORT_PATH = SQLITE_PATH.parent / "reports" / "powertrans_access_import_report.json"
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
    if serial.isdigit():
        serial = serial.lstrip("0") or "0"
    return serial


def normalize_transformer_name(value):
    text = normalize_text(value)
    text = text.replace("Μ / Σ", "ΜΣ")
    text = text.replace("Μ Σ", "ΜΣ")
    text = text.replace("Μ/Σ", "ΜΣ")
    text = text.replace("ΜΕΤΑΣΧΗΜΑΤΙΣΤΗΣ", "ΜΣ")
    text = re.sub(r"^ΜΣ\s*", "ΜΣ", text)
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
    first_initial = ""
    if len(parts) > 1:
        first_initial = parts[1][0]
    return f"{surname}|{first_initial}"


def parse_asset_transformer_display(value):
    parts = [part.strip() for part in str(value or "").split(",")]
    if len(parts) < 3:
        return None, None
    return parts[0], parts[2]


def build_access_connection():
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={ACCDB_PATH};"
    )
    return pyodbc.connect(conn_str)


def load_access_transformers():
    transformers = {}
    with build_access_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT [HVMVTransformer ID], [Υποσταθμός], [Ονομασία], [Serial No], [Τύπος] FROM tblPowerTransformers"
        )
        for row in cursor.fetchall():
            transformers[str(row[0])] = {
                "transformer_id": str(row[0]),
                "substation_name": row[1],
                "transformer_name": row[2],
                "serial_no": row[3],
                "transformer_type": row[4],
                "source": "tblPowerTransformers",
            }

        cursor.execute(
            "SELECT [HVMVTransformer ID], [Ονομασία], [Serial No] FROM qryPowerTransformersActive"
        )
        for row in cursor.fetchall():
            transformer_id = str(row[0])
            item = transformers.setdefault(
                transformer_id,
                {
                    "transformer_id": transformer_id,
                    "substation_name": None,
                    "transformer_name": None,
                    "serial_no": None,
                    "transformer_type": None,
                    "source": "qryPowerTransformersActive",
                },
            )
            if not item.get("transformer_name") and row[1]:
                item["transformer_name"] = row[1]
            if not item.get("serial_no") and row[2]:
                item["serial_no"] = row[2]

        cursor.execute(
            "SELECT DISTINCT [HVMVTransformer ID], [Transformer] FROM qryAssetTransformer"
        )
        for row in cursor.fetchall():
            transformer_id = str(row[0])
            substation_name, transformer_name = parse_asset_transformer_display(row[1])
            item = transformers.setdefault(
                transformer_id,
                {
                    "transformer_id": transformer_id,
                    "substation_name": None,
                    "transformer_name": None,
                    "serial_no": None,
                    "transformer_type": None,
                    "source": "qryAssetTransformer",
                },
            )
            if not item.get("substation_name") and substation_name:
                item["substation_name"] = substation_name
            if not item.get("transformer_name") and transformer_name:
                item["transformer_name"] = transformer_name

    return transformers


def load_access_maintainers():
    maintainers = {}
    with build_access_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ID, [Συντηρητής] FROM tblMaintenancePersonnel")
        for row in cursor.fetchall():
            maintainers[int(row[0])] = row[1]
    return maintainers


def load_access_maintenance_rows():
    rows = []
    with build_access_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ID, [Ημ/νία], [Μετασχηματιστής], [Συντηρητής], [Περιγραφή], [Ολοκληρώθηκε] FROM tblPowerTransMaintenanceData ORDER BY ID"
        )
        for row in cursor.fetchall():
            rows.append(
                {
                    "maintenance_id": int(row[0]),
                    "date": str(row[1]) if row[1] is not None else None,
                    "transformer_fk": str(row[2]).strip() if row[2] is not None else None,
                    "maintainer_fk": int(row[3]) if row[3] is not None else None,
                    "description": row[4] or "",
                    "completed": bool(row[5]) if row[5] is not None else None,
                }
            )
    return rows


def load_sqlite_transformers(conn):
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.id AS element_id,
            e.name AS element_name,
            e.serial_number,
            e.substation_id,
            s.name AS substation_name
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
        item["norm_serial"] = normalize_serial(item["serial_number"])
        item["norm_name"] = normalize_transformer_name(item["element_name"])
        item["norm_substation"] = normalize_text(item["substation_name"])
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
    backup_path = BACKUP_DIR / f"substations_before_access_powertrans_import_{timestamp}.db"
    shutil.copy2(SQLITE_PATH, backup_path)
    return backup_path


def find_matching_element(transformer, sqlite_transformers):
    access_serial = normalize_serial(transformer.get("serial_no"))
    access_substation = access_substation_key(transformer.get("substation_name"))
    access_name = normalize_transformer_name(transformer.get("transformer_name"))

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
            row for row in sqlite_transformers if row["norm_substation"] == access_substation
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


def maintenance_exists(conn, substation_id, element_id, element_name, date_value, description):
    row = conn.execute(
        """
        SELECT m.id
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        WHERE m.substation_id = ?
          AND m.name = ?
          AND m.date_time = ?
          AND me.element_id = ?
          AND COALESCE(me.element_comments, '') = COALESCE(?, '')
        LIMIT 1
        """,
        (substation_id, element_name, date_value, element_id, description),
    ).fetchone()
    return row[0] if row else None


def next_maintenance_id(conn):
    maintenance_max = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM maintenance"
    ).fetchone()[0]
    link_max = conn.execute(
        "SELECT COALESCE(MAX(maintenance_id), 0) FROM maintenance_elements"
    ).fetchone()[0]
    return max(maintenance_max, link_max) + 1


def main():
    access_transformers = load_access_transformers()
    access_maintainers = load_access_maintainers()
    access_maintenance = load_access_maintenance_rows()

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
        sqlite_transformers = load_sqlite_transformers(conn)
        sqlite_people = load_sqlite_people(conn)
        current_maintenance_id = next_maintenance_id(conn)

        for row in access_maintenance:
            if not row["date"]:
                report["unmatched_reasons"]["missing_maintenance_date"] += 1
                report["unmatched"].append(
                    {
                        "maintenance_id": row["maintenance_id"],
                        "reason": "missing_maintenance_date",
                        "transformer_fk": row["transformer_fk"],
                    }
                )
                continue

            transformer = access_transformers.get(row["transformer_fk"])
            if not transformer:
                report["unmatched_reasons"]["missing_access_transformer_lookup"] += 1
                report["unmatched"].append(
                    {
                        "maintenance_id": row["maintenance_id"],
                        "reason": "missing_access_transformer_lookup",
                        "transformer_fk": row["transformer_fk"],
                    }
                )
                continue

            element, match_method = find_matching_element(transformer, sqlite_transformers)
            if not element:
                report["unmatched_reasons"]["sqlite_transformer_not_found"] += 1
                report["unmatched"].append(
                    {
                        "maintenance_id": row["maintenance_id"],
                        "reason": "sqlite_transformer_not_found",
                        "transformer_fk": row["transformer_fk"],
                        "access_substation": transformer.get("substation_name"),
                        "access_transformer_name": transformer.get("transformer_name"),
                        "access_serial": transformer.get("serial_no"),
                        "access_source": transformer.get("source"),
                    }
                )
                continue

            report["match_methods"][match_method] += 1

            responsible_name = access_maintainers.get(row["maintainer_fk"])
            responsible_id, mapping_method = map_responsible_id(responsible_name, sqlite_people)
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

            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO maintenance (id, substation_id, name, date_time, overall_comments, responsible_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    current_maintenance_id,
                    element["substation_id"],
                    element["element_name"],
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
