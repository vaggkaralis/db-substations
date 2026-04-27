import argparse
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pyodbc


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from onedrive_hybrid_storage import sync_transformer_subelement_folders  # noqa: E402
from settings import DB_PATH  # noqa: E402


SQLITE_PATH = ROOT_DIR / DB_PATH
ACCDB_PATH = ROOT_DIR / "substation_asset_maintenance.accdb"
BACKUP_DIR = ROOT_DIR / "backups" / "access_imports"
REPORT_PATH = (
    ROOT_DIR / "reports" / "access_transformer_subelements_backfill_report.json"
)

TRANSFORMER_TYPE_MARKERS = ("μετασχηματιστ", "transformer", "150/20")
MOTOR_DRIVE_TYPE = "Motor Drive"
MOTOR_DRIVE_NAME = "Motor Drive"

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


def normalize_serial(value):
    serial = re.sub(r"[^A-Z0-9]", "", normalize_text(value))
    if serial.isdigit():
        serial = serial.lstrip("0") or "0"
    return serial


def normalize_transformer_name(value):
    text = normalize_text(value)
    text = text.replace("Μ Σ", "ΜΣ")
    text = text.replace("Μ Σ ", "ΜΣ")
    text = text.replace("ΜΕΤΑΣΧΗΜΑΤΙΣΤΗΣ", "ΜΣ")
    text = re.sub(r"^ΜΣ\s*", "ΜΣ", text)
    return text


def access_substation_key(value):
    base = normalize_text(value)
    return ACCESS_TO_SQLITE_SUBSTATION.get(base, base)


def text_similarity(left, right):
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def normalize_vector_group(value):
    return normalize_text(value).replace(" ", "")


def backup_sqlite_db():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIR / f"substations_before_transformer_subelements_{timestamp}.db"
    )
    shutil.copy2(SQLITE_PATH, backup_path)
    return backup_path


def build_access_connection():
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};" f"DBQ={ACCDB_PATH};"
    )
    return pyodbc.connect(conn_str)


def ensure_required_columns(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(elements)")
    element_columns = {row[1] for row in cursor.fetchall()}
    missing_elements = {"parent_element_id", "vector_group"} - element_columns
    if missing_elements:
        raise RuntimeError(
            "elements table is missing required columns: "
            + ", ".join(sorted(missing_elements))
        )

    cursor.execute("PRAGMA table_info(element_models)")
    model_columns = {row[1] for row in cursor.fetchall()}
    if "drive_mechanism" not in model_columns:
        raise RuntimeError("element_models table is missing drive_mechanism")


def parse_asset_transformer_display(value):
    parts = [part.strip() for part in str(value or "").split(",")]
    if len(parts) < 3:
        return None, None
    return parts[0], parts[2]


def load_access_transformer_models(cursor):
    rows = cursor.execute("SELECT * FROM tblPowerTransformersModel").fetchall()
    models = []
    for row in rows:
        models.append(
            {
                "access_model_id": int(row[0]),
                "manufacturer": (row[1] or "").strip(),
                "model_name": (row[2] or "").strip(),
                "rated_power": row[3],
                "connection_group": (row[4] or "").strip(),
                "oltc": (row[15] or "").strip(),
            }
        )
    return models


def load_access_transformers(cursor, models_by_id):
    transformers = {}

    rows = cursor.execute("SELECT * FROM tblPowerTransformers").fetchall()
    for row in rows:
        transformer_id = str(row[0]).strip()
        model_ref = int(row[3]) if row[3] not in (None, "") else None
        item = {
            "transformer_id": transformer_id,
            "substation_name": row[1],
            "transformer_name": row[2],
            "access_model_id": model_ref,
            "serial_no": row[4],
            "model_name": (row[5] or "").strip(),
            "manufacture_year": row[6],
            "rated_power": row[7],
            "connection_group": (row[8] or "").strip(),
            "oltc": (row[19] or "").strip(),
            "source": "tblPowerTransformers",
        }
        if model_ref and model_ref in models_by_id:
            item["model"] = models_by_id[model_ref]
        transformers[transformer_id] = item

    try:
        rows = cursor.execute(
            "SELECT [HVMVTransformer ID], [Ονομασία], [Serial No] "
            "FROM qryPowerTransformersActive"
        ).fetchall()
        for row in rows:
            transformer_id = str(row[0]).strip()
            item = transformers.setdefault(
                transformer_id,
                {
                    "transformer_id": transformer_id,
                    "substation_name": None,
                    "transformer_name": None,
                    "access_model_id": None,
                    "serial_no": None,
                    "model_name": "",
                    "manufacture_year": None,
                    "rated_power": None,
                    "connection_group": "",
                    "oltc": "",
                    "source": "qryPowerTransformersActive",
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
            transformer_id = str(row[0]).strip()
            substation_name, transformer_name = parse_asset_transformer_display(row[1])
            item = transformers.setdefault(
                transformer_id,
                {
                    "transformer_id": transformer_id,
                    "substation_name": None,
                    "transformer_name": None,
                    "access_model_id": None,
                    "serial_no": None,
                    "model_name": "",
                    "manufacture_year": None,
                    "rated_power": None,
                    "connection_group": "",
                    "oltc": "",
                    "source": "qryAssetTransformer",
                },
            )
            if not item.get("substation_name") and substation_name:
                item["substation_name"] = substation_name
            if not item.get("transformer_name") and transformer_name:
                item["transformer_name"] = transformer_name
    except Exception:
        pass

    for item in transformers.values():
        model = models_by_id.get(item.get("access_model_id"))
        if model:
            item.setdefault("model", model)
            if not item.get("model_name"):
                item["model_name"] = model.get("model_name") or ""
            if not item.get("connection_group"):
                item["connection_group"] = model.get("connection_group") or ""
            if not item.get("oltc"):
                item["oltc"] = model.get("oltc") or ""
        item["norm_serial"] = normalize_serial(item.get("serial_no"))
        item["norm_substation"] = access_substation_key(item.get("substation_name"))
        item["norm_name"] = normalize_transformer_name(item.get("transformer_name"))

    return list(transformers.values())


def load_sqlite_transformers(conn):
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.id AS element_id,
            e.substation_id,
            e.parent_element_id,
            e.name AS element_name,
            e.serial_number,
            e.element_type,
            e.element_model_id,
            e.model AS element_model_name,
            e.manufacturer AS element_manufacturer,
            e.manufacture_year,
            e.voltage_level,
            e.installation_space,
            e.operating_status,
            e.maintenance_cycle,
            e.gate,
            e.hemizygos,
            e.vector_group,
            s.name AS substation_name,
            em.model_name AS model_name,
            em.manufacturer AS model_manufacturer,
            em.connection_group AS model_connection_group
        FROM elements e
        JOIN substations s ON s.id = e.substation_id
        LEFT JOIN element_models em ON em.id = e.element_model_id
        WHERE COALESCE(e.parent_element_id, 0) = 0
          AND (
              LOWER(COALESCE(e.element_type, '')) LIKE '%μετασχηματιστ%'
              OR LOWER(COALESCE(e.element_type, '')) LIKE '%transformer%'
              OR LOWER(COALESCE(e.element_type, '')) LIKE '%150/20%'
              OR e.name LIKE 'ΜΣ%'
          )
        ORDER BY s.name, e.name
        """
    ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        item["norm_serial"] = normalize_serial(item.get("serial_number"))
        item["norm_substation"] = normalize_text(item.get("substation_name"))
        item["norm_name"] = normalize_transformer_name(item.get("element_name"))
        local_model_name = (
            item.get("model_name") or item.get("element_model_name") or ""
        )
        local_manufacturer = (
            item.get("model_manufacturer") or item.get("element_manufacturer") or ""
        )
        item["local_model_name"] = local_model_name
        item["local_model_manufacturer"] = local_manufacturer
        result.append(item)
    return result


def find_matching_transformer(access_transformer, sqlite_transformers):
    access_serial = access_transformer.get("norm_serial")
    access_substation = access_transformer.get("norm_substation")
    access_name = access_transformer.get("norm_name")

    serial_candidates = []
    if access_serial:
        serial_candidates = [
            row
            for row in sqlite_transformers
            if row.get("norm_serial") == access_serial
        ]
        if len(serial_candidates) == 1:
            return serial_candidates[0], "serial"

    compatible_substations = []
    if access_substation:
        compatible_substations = [
            row
            for row in sqlite_transformers
            if row.get("norm_substation") == access_substation
        ]
        if not compatible_substations:
            compatible_substations = [
                row
                for row in sqlite_transformers
                if access_substation in row.get("norm_substation", "")
                or row.get("norm_substation", "") in access_substation
            ]

    if compatible_substations and access_name:
        name_matches = [
            row for row in compatible_substations if row.get("norm_name") == access_name
        ]
        if len(name_matches) == 1:
            return name_matches[0], "substation+name"

    if compatible_substations and access_serial:
        serial_matches = [
            row
            for row in compatible_substations
            if row.get("norm_serial") == access_serial
        ]
        if len(serial_matches) == 1:
            return serial_matches[0], "substation+serial"

    return None, None


def score_access_model(local_model_name, local_manufacturer, access_model):
    score = 0.0
    normalized_local_name = normalize_text(local_model_name)
    normalized_access_name = normalize_text(access_model.get("model_name"))
    normalized_local_manufacturer = normalize_text(local_manufacturer)
    normalized_access_manufacturer = normalize_text(access_model.get("manufacturer"))

    if (
        normalized_local_manufacturer
        and normalized_access_manufacturer
        and normalized_local_manufacturer == normalized_access_manufacturer
    ):
        score += 3.0
    if normalized_local_name and normalized_access_name:
        if (
            normalized_access_name in normalized_local_name
            or normalized_local_name in normalized_access_name
        ):
            score += 5.0
        score += text_similarity(normalized_local_name, normalized_access_name) * 4.0
    return score


def best_access_model_for_sqlite_transformer(sqlite_transformer, access_models):
    local_model_name = sqlite_transformer.get("local_model_name") or ""
    local_manufacturer = sqlite_transformer.get("local_model_manufacturer") or ""
    if not local_model_name:
        return None, None

    ranked = []
    for access_model in access_models:
        score = score_access_model(local_model_name, local_manufacturer, access_model)
        if score > 0:
            ranked.append((score, access_model))
    ranked.sort(key=lambda item: (-item[0], item[1]["access_model_id"]))
    if not ranked:
        return None, None

    best_score, best_candidate = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else None
    if best_score < 6.0:
        return None, None
    if second_score is not None and best_score - second_score < 1.0:
        return None, None
    return best_candidate, "model"


def build_motor_drive_specs(access_models):
    grouped = defaultdict(list)
    for model in access_models:
        oltc = (model.get("oltc") or "").strip()
        if oltc:
            grouped[oltc].append(model)

    specs = []
    for oltc, items in sorted(
        grouped.items(), key=lambda item: normalize_text(item[0])
    ):
        manufacturers = [
            item.get("manufacturer") or "" for item in items if item.get("manufacturer")
        ]
        manufacturer = (
            Counter(manufacturers).most_common(1)[0][0] if manufacturers else ""
        )
        specs.append(
            {
                "oltc": oltc,
                "manufacturer": manufacturer,
                "source_model_ids": sorted({item["access_model_id"] for item in items}),
            }
        )
    return specs


def ensure_motor_drive_models(conn, specs, *, dry_run=False):
    cursor = conn.cursor()
    model_map = {}
    created = []
    reused = []

    for spec in specs:
        cursor.execute(
            """
            SELECT id, manufacturer
            FROM element_models
            WHERE element_category=? AND TRIM(model_name)=TRIM(?)
            ORDER BY CASE WHEN TRIM(COALESCE(manufacturer, ''))=TRIM(?) THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (MOTOR_DRIVE_TYPE, spec["oltc"], spec["manufacturer"]),
        )
        row = cursor.fetchone()
        if row:
            model_map[spec["oltc"]] = row[0]
            reused.append(
                {
                    "id": row[0],
                    "oltc": spec["oltc"],
                    "manufacturer": row[1] or "",
                }
            )
            continue

        if dry_run:
            model_map[spec["oltc"]] = None
            created.append(
                {
                    "id": None,
                    "oltc": spec["oltc"],
                    "manufacturer": spec["manufacturer"],
                }
            )
            continue

        cursor.execute(
            """
            INSERT INTO element_models (
                element_category,
                model_name,
                manufacturer,
                maintenance_cycle,
                drive_mechanism
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                MOTOR_DRIVE_TYPE,
                spec["oltc"],
                spec["manufacturer"],
                0,
                spec["oltc"],
            ),
        )
        model_id = cursor.lastrowid
        model_map[spec["oltc"]] = model_id
        created.append(
            {
                "id": model_id,
                "oltc": spec["oltc"],
                "manufacturer": spec["manufacturer"],
            }
        )

    return model_map, created, reused


def maybe_update_vector_group(
    conn,
    sqlite_transformer,
    desired_vector_group,
    strategy,
    updates,
    conflicts,
    *,
    dry_run=False,
):
    desired_value = (desired_vector_group or "").strip()
    if not desired_value:
        return False

    current_value = (sqlite_transformer.get("vector_group") or "").strip()
    if current_value:
        if normalize_vector_group(current_value) == normalize_vector_group(
            desired_value
        ):
            return False
        conflicts.append(
            {
                "element_id": sqlite_transformer["element_id"],
                "element_name": sqlite_transformer["element_name"],
                "current_vector_group": current_value,
                "access_vector_group": desired_value,
                "strategy": strategy,
            }
        )
        return False

    if not dry_run:
        conn.execute(
            "UPDATE elements SET vector_group=? WHERE id=?",
            (desired_value, sqlite_transformer["element_id"]),
        )
    sqlite_transformer["vector_group"] = desired_value
    updates.append(
        {
            "element_id": sqlite_transformer["element_id"],
            "element_name": sqlite_transformer["element_name"],
            "vector_group": desired_value,
            "strategy": strategy,
        }
    )
    return True


def upsert_motor_drive_child(
    conn,
    sqlite_transformer,
    model_id,
    model_name,
    manufacturer,
    strategy,
    linked_children,
    skipped_children,
    *,
    dry_run=False,
):
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT id, name, element_model_id, model, manufacturer
        FROM elements
        WHERE parent_element_id=? AND element_type=?
        ORDER BY id
        """,
        (sqlite_transformer["element_id"], MOTOR_DRIVE_TYPE),
    ).fetchall()

    if len(rows) > 1:
        skipped_children.append(
            {
                "element_id": sqlite_transformer["element_id"],
                "element_name": sqlite_transformer["element_name"],
                "reason": "multiple_existing_motor_drive_children",
                "strategy": strategy,
            }
        )
        return False

    if rows:
        child_id, child_name, child_model_id, child_model_name, child_manufacturer = (
            rows[0]
        )
        changed_fields = {}
        if model_id is not None and child_model_id != model_id:
            changed_fields["element_model_id"] = model_id
        if model_name and (child_model_name or "").strip() != model_name:
            changed_fields["model"] = model_name
        if manufacturer and not (child_manufacturer or "").strip():
            changed_fields["manufacturer"] = manufacturer
        if not (child_name or "").strip():
            changed_fields["name"] = MOTOR_DRIVE_NAME

        if not changed_fields:
            return False

        if not dry_run:
            assignments = ", ".join(f"{column}=?" for column in changed_fields)
            cursor.execute(
                f"UPDATE elements SET {assignments} WHERE id=?",
                list(changed_fields.values()) + [child_id],
            )
        linked_children.append(
            {
                "child_id": child_id,
                "parent_id": sqlite_transformer["element_id"],
                "parent_name": sqlite_transformer["element_name"],
                "action": "update",
                "fields": changed_fields,
                "strategy": strategy,
            }
        )
        return True

    if not dry_run:
        cursor.execute(
            """
            INSERT INTO elements (
                substation_id,
                parent_element_id,
                element_type,
                name,
                voltage_level,
                manufacturer,
                model,
                installation_space,
                operating_status,
                maintenance_cycle,
                element_model_id,
                manufacture_year,
                gate,
                hemizygos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sqlite_transformer["substation_id"],
                sqlite_transformer["element_id"],
                MOTOR_DRIVE_TYPE,
                MOTOR_DRIVE_NAME,
                sqlite_transformer.get("voltage_level") or "",
                manufacturer or "",
                model_name or "",
                sqlite_transformer.get("installation_space") or "",
                sqlite_transformer.get("operating_status") or "Ενεργή",
                0,
                model_id,
                sqlite_transformer.get("manufacture_year") or "",
                sqlite_transformer.get("gate") or "",
                sqlite_transformer.get("hemizygos") or "",
            ),
        )
        child_id = cursor.lastrowid
    else:
        child_id = None

    linked_children.append(
        {
            "child_id": child_id,
            "parent_id": sqlite_transformer["element_id"],
            "parent_name": sqlite_transformer["element_name"],
            "action": "insert",
            "fields": {
                "element_model_id": model_id,
                "model": model_name,
                "manufacturer": manufacturer,
            },
            "strategy": strategy,
        }
    )
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    ensure_required_columns(sqlite_conn)

    backup_path = None if args.dry_run else backup_sqlite_db()

    access_conn = build_access_connection()
    access_cursor = access_conn.cursor()
    access_models = load_access_transformer_models(access_cursor)
    access_models_by_id = {item["access_model_id"]: item for item in access_models}
    access_transformers = load_access_transformers(access_cursor, access_models_by_id)

    sqlite_transformers = load_sqlite_transformers(sqlite_conn)
    matched_sqlite_ids = set()
    touched_substations = set()

    motor_drive_specs = build_motor_drive_specs(access_models)
    model_map, created_models, reused_models = ensure_motor_drive_models(
        sqlite_conn, motor_drive_specs, dry_run=args.dry_run
    )

    vector_group_updates = []
    vector_group_conflicts = []
    linked_children = []
    skipped_children = []
    unmatched_access_transformers = []
    matched_access_transformers = []

    for access_transformer in access_transformers:
        sqlite_transformer, strategy = find_matching_transformer(
            access_transformer, sqlite_transformers
        )
        access_model = access_models_by_id.get(
            access_transformer.get("access_model_id")
        )

        desired_vector_group = access_transformer.get("connection_group") or (
            access_model.get("connection_group") if access_model else ""
        )
        desired_oltc = access_transformer.get("oltc") or (
            access_model.get("oltc") if access_model else ""
        )

        if not sqlite_transformer:
            unmatched_access_transformers.append(
                {
                    "transformer_id": access_transformer["transformer_id"],
                    "substation_name": access_transformer.get("substation_name"),
                    "transformer_name": access_transformer.get("transformer_name"),
                    "serial_no": access_transformer.get("serial_no"),
                    "model_name": access_transformer.get("model_name"),
                    "connection_group": desired_vector_group,
                    "oltc": desired_oltc,
                }
            )
            continue

        matched_sqlite_ids.add(sqlite_transformer["element_id"])
        touched_substations.add(sqlite_transformer["substation_id"])
        matched_access_transformers.append(
            {
                "transformer_id": access_transformer["transformer_id"],
                "element_id": sqlite_transformer["element_id"],
                "element_name": sqlite_transformer["element_name"],
                "strategy": strategy,
            }
        )

        maybe_update_vector_group(
            sqlite_conn,
            sqlite_transformer,
            desired_vector_group,
            strategy,
            vector_group_updates,
            vector_group_conflicts,
            dry_run=args.dry_run,
        )

        if desired_oltc:
            upsert_motor_drive_child(
                sqlite_conn,
                sqlite_transformer,
                model_map.get(desired_oltc),
                desired_oltc,
                (access_model.get("manufacturer") if access_model else "") or "",
                strategy,
                linked_children,
                skipped_children,
                dry_run=args.dry_run,
            )

    fallback_model_updates = []
    fallback_model_children = []
    for sqlite_transformer in sqlite_transformers:
        if sqlite_transformer["element_id"] in matched_sqlite_ids:
            continue
        access_model, strategy = best_access_model_for_sqlite_transformer(
            sqlite_transformer, access_models
        )
        if access_model is None:
            continue

        touched_substations.add(sqlite_transformer["substation_id"])
        if maybe_update_vector_group(
            sqlite_conn,
            sqlite_transformer,
            access_model.get("connection_group"),
            strategy,
            fallback_model_updates,
            vector_group_conflicts,
            dry_run=args.dry_run,
        ):
            pass

        if access_model.get("oltc"):
            before_count = len(linked_children)
            if upsert_motor_drive_child(
                sqlite_conn,
                sqlite_transformer,
                model_map.get(access_model["oltc"]),
                access_model["oltc"],
                access_model.get("manufacturer") or "",
                strategy,
                linked_children,
                skipped_children,
                dry_run=args.dry_run,
            ):
                if len(linked_children) > before_count:
                    fallback_model_children.append(linked_children[-1])

    if not args.dry_run:
        sqlite_conn.commit()
        for substation_id in sorted(touched_substations):
            try:
                sync_transformer_subelement_folders(
                    sqlite_conn, substation_id, db_path=str(SQLITE_PATH)
                )
            except Exception:
                pass
        sqlite_conn.commit()

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "sqlite_path": str(SQLITE_PATH),
        "access_path": str(ACCDB_PATH),
        "backup_path": str(backup_path) if backup_path else None,
        "counts": {
            "access_transformers": len(access_transformers),
            "sqlite_transformers": len(sqlite_transformers),
            "matched_access_transformers": len(matched_access_transformers),
            "unmatched_access_transformers": len(unmatched_access_transformers),
            "motor_drive_model_specs": len(motor_drive_specs),
            "created_motor_drive_models": len(created_models),
            "reused_motor_drive_models": len(reused_models),
            "direct_vector_group_updates": len(vector_group_updates),
            "fallback_vector_group_updates": len(fallback_model_updates),
            "linked_motor_drive_children": len(linked_children),
            "skipped_motor_drive_children": len(skipped_children),
            "vector_group_conflicts": len(vector_group_conflicts),
        },
        "created_motor_drive_models": created_models,
        "reused_motor_drive_models": reused_models,
        "matched_access_transformers": matched_access_transformers,
        "unmatched_access_transformers": unmatched_access_transformers,
        "direct_vector_group_updates": vector_group_updates,
        "fallback_vector_group_updates": fallback_model_updates,
        "linked_motor_drive_children": linked_children,
        "fallback_model_children": fallback_model_children,
        "skipped_motor_drive_children": skipped_children,
        "vector_group_conflicts": vector_group_conflicts,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    if backup_path:
        print(f"Backup: {backup_path}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
