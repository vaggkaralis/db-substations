import json
import re
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import import_hvcb_maintenance as hvcb
import import_mvcb_maintenance as mvcb
import import_powertrans_maintenance as powertrans
from access_gate_utils import (
    build_access_asset_gate_maps,
    find_hv_gate,
    find_mv_gate,
    find_transformer_gate,
    format_gate_label,
)
from maintenance_email_importer import _find_people_in_body


ACCDB_PATH = powertrans.ACCDB_PATH
SQLITE_PATH = powertrans.SQLITE_PATH
REPORT_PATH = SQLITE_PATH.parent / "reports" / "access_import_repair_report.json"
BACKUP_DIR = SQLITE_PATH.parent / "backups" / "access_imports"


def backup_sqlite_db():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"substations_before_access_import_repair_{timestamp}.db"
    shutil.copy2(SQLITE_PATH, backup_path)
    return backup_path


def find_existing_maintenance(conn, substation_id, element_id, date_value, description):
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
        ORDER BY m.id DESC
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


def repair_powertrans(conn, gate_maps, report):
    access_transformers = powertrans.load_access_transformers()
    access_maintainers = powertrans.load_access_maintainers()
    access_rows = powertrans.load_access_maintenance_rows()
    sqlite_transformers = powertrans.load_sqlite_transformers(conn)
    sqlite_people = powertrans.load_sqlite_people(conn)

    for row in access_rows:
        transformer = access_transformers.get(row["transformer_fk"])
        if not transformer or not row.get("date"):
            continue
        element, _ = powertrans.find_matching_element(transformer, sqlite_transformers)
        if not element:
            continue
        maintenance_id = find_existing_maintenance(
            conn,
            element["substation_id"],
            element["element_id"],
            row["date"],
            row["description"],
        )
        if not maintenance_id:
            continue

        responsible_name = access_maintainers.get(row.get("maintainer_fk"))
        responsible_id, _ = powertrans.map_responsible_id(
            responsible_name, sqlite_people
        )
        conn.execute(
            "UPDATE maintenance SET name = NULL, date_time = ?, overall_comments = ?, responsible_id = ? WHERE id = ?",
            (row["date"], row["description"], responsible_id, maintenance_id),
        )
        conn.execute(
            "UPDATE maintenance_elements SET element_comments = ? WHERE maintenance_id = ? AND element_id = ?",
            (row["description"], maintenance_id, element["element_id"]),
        )
        crew_ids = sync_maintenance_people(
            conn, maintenance_id, responsible_id, row["description"]
        )
        report["responsible_repairs"] += 1 if responsible_id else 0
        report["crew_repairs"] += len(crew_ids)

        gate_number = find_transformer_gate(
            gate_maps,
            transformer.get("substation_name"),
            transformer.get("transformer_name"),
            transformer.get("serial_no"),
        )
        desired_gate = format_gate_label(gate_number)
        if desired_gate:
            current_gate = conn.execute(
                "SELECT gate FROM elements WHERE id = ?", (element["element_id"],)
            ).fetchone()[0]
            if current_gate != desired_gate:
                conn.execute(
                    "UPDATE elements SET gate = ? WHERE id = ?",
                    (desired_gate, element["element_id"]),
                )
                report["gate_updates"] += 1

        sync_element_maintenance_date(conn, element["element_id"])
        sync_substation_last_maintenance(conn, element["substation_id"])
        report["maintenance_rows_fixed"] += 1


def repair_hvcb(conn, gate_maps, report):
    access_rows = hvcb.load_access_maintenance_rows()
    sqlite_breakers = hvcb.load_sqlite_breakers(conn)
    sqlite_people = hvcb.load_sqlite_people(conn)

    for row in access_rows:
        if not row.get("date") or not row.get("breaker_fk"):
            continue
        element, _ = hvcb.find_matching_element(row, sqlite_breakers)
        if not element:
            continue
        maintenance_id = find_existing_maintenance(
            conn,
            element["substation_id"],
            element["element_id"],
            row["date"],
            row["description"],
        )
        if not maintenance_id:
            continue

        responsible_id, _ = hvcb.map_responsible_id(
            row.get("access_maintainer_name"), sqlite_people
        )
        conn.execute(
            "UPDATE maintenance SET name = NULL, date_time = ?, overall_comments = ?, responsible_id = ? WHERE id = ?",
            (row["date"], row["description"], responsible_id, maintenance_id),
        )
        conn.execute(
            "UPDATE maintenance_elements SET element_comments = ? WHERE maintenance_id = ? AND element_id = ?",
            (row["description"], maintenance_id, element["element_id"]),
        )
        crew_ids = sync_maintenance_people(
            conn, maintenance_id, responsible_id, row["description"]
        )
        report["responsible_repairs"] += 1 if responsible_id else 0
        report["crew_repairs"] += len(crew_ids)

        gate_number = find_hv_gate(
            gate_maps,
            row.get("access_substation_name"),
            row.get("access_breaker_name"),
            row.get("access_serial"),
        )
        desired_gate = format_gate_label(gate_number)
        if desired_gate:
            current_gate = conn.execute(
                "SELECT gate FROM elements WHERE id = ?", (element["element_id"],)
            ).fetchone()[0]
            if current_gate != desired_gate:
                conn.execute(
                    "UPDATE elements SET gate = ? WHERE id = ?",
                    (desired_gate, element["element_id"]),
                )
                report["gate_updates"] += 1

        sync_element_maintenance_date(conn, element["element_id"])
        sync_substation_last_maintenance(conn, element["substation_id"])
        report["maintenance_rows_fixed"] += 1


def repair_mvcb(conn, gate_maps, report):
    access_rows = mvcb.load_access_maintenance_rows()
    sqlite_breakers = mvcb.load_sqlite_breakers(conn)
    sqlite_people = mvcb.load_sqlite_people(conn)

    for row in access_rows:
        if not row.get("date") or not row.get("breaker_fk"):
            continue
        element, _ = mvcb.find_matching_element(row, sqlite_breakers)
        if not element:
            continue
        maintenance_id = find_existing_maintenance(
            conn,
            element["substation_id"],
            element["element_id"],
            row["date"],
            row["description"],
        )
        if not maintenance_id:
            continue

        responsible_id, _ = mvcb.map_responsible_id(
            row.get("access_maintainer_name"), sqlite_people
        )
        conn.execute(
            "UPDATE maintenance SET name = NULL, date_time = ?, overall_comments = ?, responsible_id = ? WHERE id = ?",
            (row["date"], row["description"], responsible_id, maintenance_id),
        )
        conn.execute(
            "UPDATE maintenance_elements SET element_comments = ? WHERE maintenance_id = ? AND element_id = ?",
            (row["description"], maintenance_id, element["element_id"]),
        )
        crew_ids = sync_maintenance_people(
            conn, maintenance_id, responsible_id, row["description"]
        )
        report["responsible_repairs"] += 1 if responsible_id else 0
        report["crew_repairs"] += len(crew_ids)

        gate_number = find_mv_gate(
            gate_maps,
            row.get("access_substation_name"),
            row.get("access_breaker_name"),
            row.get("access_serial"),
        )
        desired_gate = format_gate_label(
            gate_number, is_interconnection=element.get("is_main_switch") == 2
        )
        if desired_gate:
            current_gate = conn.execute(
                "SELECT gate FROM elements WHERE id = ?", (element["element_id"],)
            ).fetchone()[0]
            if current_gate != desired_gate:
                conn.execute(
                    "UPDATE elements SET gate = ? WHERE id = ?",
                    (desired_gate, element["element_id"]),
                )
                report["gate_updates"] += 1

        sync_element_maintenance_date(conn, element["element_id"])
        sync_substation_last_maintenance(conn, element["substation_id"])
        report["maintenance_rows_fixed"] += 1


def main():
    backup_path = backup_sqlite_db()
    gate_maps = build_access_asset_gate_maps(ACCDB_PATH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = Counter()
    report["backup_path"] = str(backup_path)

    with sqlite3.connect(SQLITE_PATH) as conn:
        repair_powertrans(conn, gate_maps, report)
        repair_hvcb(conn, gate_maps, report)
        repair_mvcb(conn, gate_maps, report)

        normalized_interconnection_gates = 0
        rows = conn.execute(
            "SELECT id, gate FROM elements WHERE element_type='Διακόπτης ΜΤ' AND is_main_switch=2 AND gate IS NOT NULL AND TRIM(gate)<>''"
        ).fetchall()
        for element_id, gate in rows:
            match = re.fullmatch(r"\s*ΠΥΛΗ\s+(\d+)\s*", gate or "")
            if not match:
                continue
            gate_number = int(match.group(1))
            conn.execute(
                "UPDATE elements SET gate = ? WHERE id = ?",
                (f"ΠΥΛΗ {gate_number}-{gate_number + 1}", element_id),
            )
            normalized_interconnection_gates += 1
        report["normalized_interconnection_gates"] = normalized_interconnection_gates

        conn.execute(
            """
            UPDATE elements
            SET maintenance_date = (
                SELECT MAX(m.date_time)
                FROM maintenance m
                JOIN maintenance_elements me ON me.maintenance_id = m.id
                WHERE me.element_id = elements.id
            )
            WHERE id IN (SELECT DISTINCT element_id FROM maintenance_elements)
            """
        )
        conn.execute(
            """
            UPDATE substations
            SET last_maintenance = (
                SELECT MAX(m.date_time)
                FROM maintenance m
                WHERE m.substation_id = substations.id
            )
            """
        )
        conn.commit()

    payload = dict(report)
    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
