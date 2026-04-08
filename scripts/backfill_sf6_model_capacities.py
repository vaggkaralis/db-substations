import json
import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT_DIR / "substations.db"
BACKUP_DIR = ROOT_DIR / "backups" / "access_imports"
REPORT_PATH = ROOT_DIR / "reports" / "sf6_capacity_backfill_report.json"


def normalize_text(value):
    text = str(value or "").strip().upper()
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
    return " ".join(text.split())


# These capacities were traced from `substation_asset_maintenance.accdb`.
# The Access source exposes them in `tblHVCBModel`, `tblMVCBModel`, and for
# Siemens GIS variants in `tblHVCBModel` as 175 kg / 230 kg. Where the SQLite
# model catalog is less specific than Access, this table uses the best verified
# mapping for the current SQLite model rows.
SF6_CAPACITY_BY_MODEL = {
    (normalize_text("ABB"), normalize_text("ABB ADDA LTB 170 I")): 9.0,
    (normalize_text("ABB"), normalize_text("ABB HA1/ZC-24-12-12, 1250A")): 1.2,
    (normalize_text("ABB"), normalize_text("ABB HA2/ZC-24-12-25, 1250A")): 2.0,
    (normalize_text("ABB"), normalize_text("ABB HPL 170/31A1")): 9.0,
    (normalize_text("ABB"), normalize_text("ABB LTB 170D1/B")): 15.0,
    (normalize_text("ABB"), normalize_text("ABB OHB 36.20.25, 2000A")): 1.25,
    (normalize_text("ABB"), normalize_text("ABB SACE HA1/WS-24-06-12, 630A")): 1.2,
    (normalize_text("ABB"), normalize_text("ABB SACE HA3/ZC 24-25-25, 2500A")): 2.0,
    (normalize_text("ABB"), normalize_text("ABB SACE SFA 24-06-12 (SFAS/R)")): 1.2,
    (normalize_text("ABB"), normalize_text("ABB SACE SFA 24-12-12 (SFAS/R)")): 1.3,
    (normalize_text("ABB"), normalize_text("ABB SACE SFAS R 240612")): 1.2,
    (normalize_text("ABB"), normalize_text("ABB SACE SFAS R 241212")): 1.3,
    (normalize_text("ABB"), normalize_text("ABB SACE SFAS/R 24-06-12")): 1.2,
    (normalize_text("ABB"), normalize_text("ABB SFE 24-20-25, 2000A")): 2.0,
    (normalize_text("AEG"), normalize_text("AEG S1-170")): 15.0,
    (normalize_text("ALSTOM"), normalize_text("ALSTOM GL 313 F1/4031 P")): 11.9,
    (normalize_text("AREVA"), normalize_text("AREVA GL 313 F1")): 15.0,
    (
        normalize_text("MAGRINI"),
        normalize_text("Magrini Galileo 36 GI-E25, 1250A"),
    ): 1.2,
    (
        normalize_text("MAGRINI"),
        normalize_text("Magrini Galileo 36 GI-E25, 2000A"),
    ): 1.2,
    (
        normalize_text("MERLIN GERIN"),
        normalize_text("Merlin Gerin 36 GI-E25, 1250A"),
    ): 1.2,
    (normalize_text("MITSUBISHI"), normalize_text("Mitsubishi 140-SFL-750L")): 15.0,
    (
        normalize_text("NUOVA MAGRINI GALILEO"),
        normalize_text("NUOVA MAGRINI GALILEO 170 MHD 1P"),
    ): 12.0,
    (normalize_text("SIEMENS"), normalize_text("SIEMENS 3 AQ1")): 9.6,
    (normalize_text("SIEMENS"), normalize_text("Siemens")): 175.0,
    (normalize_text("SIEMENS"), normalize_text("Siemens 3AP1FG")): 9.6,
    (normalize_text("SIEMENS"), normalize_text("Siemens 8DN2022")): 175.0,
    (normalize_text("Υ/Δ"), normalize_text("GL 313 F1/4031 P")): 11.9,
    (normalize_text("GL 313 F1/4031 P"), normalize_text("GL 313 F1/4031 P")): 11.9,
}


MODEL_NAME_FALLBACKS = {
    normalize_text("ABB ADDA LTB 170 I"): 9.0,
    normalize_text("ABB HA1/ZC-24-12-12, 1250A"): 1.2,
    normalize_text("ABB HA2/ZC-24-12-25, 1250A"): 2.0,
    normalize_text("ABB HPL 170/31A1"): 9.0,
    normalize_text("ABB LTB 170D1/B"): 15.0,
    normalize_text("ABB OHB 36.20.25, 2000A"): 1.25,
    normalize_text("ABB SACE HA1/WS-24-06-12, 630A"): 1.2,
    normalize_text("ABB SACE HA3/ZC 24-25-25, 2500A"): 2.0,
    normalize_text("ABB SACE SFA 24-06-12 (SFAS/R)"): 1.2,
    normalize_text("ABB SACE SFA 24-12-12 (SFAS/R)"): 1.3,
    normalize_text("ABB SACE SFAS R 240612"): 1.2,
    normalize_text("ABB SACE SFAS R 241212"): 1.3,
    normalize_text("ABB SACE SFAS/R 24-06-12"): 1.2,
    normalize_text("ABB SFE 24-20-25, 2000A"): 2.0,
    normalize_text("AEG S1-170"): 15.0,
    normalize_text("ALSTOM GL 313 F1/4031 P"): 11.9,
    normalize_text("AREVA GL 313 F1"): 15.0,
    normalize_text("GL 313 F1/4031 P"): 11.9,
    normalize_text("Magrini Galileo 36 GI-E25, 1250A"): 1.2,
    normalize_text("Magrini Galileo 36 GI-E25, 2000A"): 1.2,
    normalize_text("Merlin Gerin 36 GI-E25, 1250A"): 1.2,
    normalize_text("Mitsubishi 140-SFL-750L"): 15.0,
    normalize_text("NUOVA MAGRINI GALILEO 170 MHD 1P"): 12.0,
    normalize_text("SIEMENS 3 AQ1"): 9.6,
    normalize_text("Siemens"): 175.0,
    normalize_text("Siemens 3AP1FG"): 9.6,
    normalize_text("Siemens 8DN2022"): 175.0,
}


def backup_sqlite_db() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIR / f"substations_before_sf6_capacity_backfill_{timestamp}.db"
    )
    shutil.copy2(SQLITE_PATH, backup_path)
    return backup_path


def installed_total(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        """
        SELECT SUM(COALESCE(em.sf6_capacity_kg, 0))
        FROM elements e
        LEFT JOIN element_models em ON em.id = e.element_model_id
        WHERE e.operating_status = 'Ενεργή'
          AND e.breaker_category = 'SF6'
          AND e.element_type IN ('Διακόπτης ΥΤ', 'Διακόπτης ΜΤ')
        """
    ).fetchone()
    return float(row[0] or 0.0)


def resolve_capacity(manufacturer, model_name):
    norm_manufacturer = normalize_text(manufacturer)
    norm_model_name = normalize_text(model_name)
    direct = SF6_CAPACITY_BY_MODEL.get((norm_manufacturer, norm_model_name))
    if direct is not None:
        return direct, "direct"

    fallback = MODEL_NAME_FALLBACKS.get(norm_model_name)
    if fallback is not None:
        return fallback, "model_name_fallback"

    return None, None


def main():
    backup_path = backup_sqlite_db()
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    before_total = installed_total(conn)
    model_rows = conn.execute(
        """
        SELECT id, manufacturer, model_name, sf6_capacity_kg
        FROM element_models
        WHERE breaker_category = 'SF6'
        ORDER BY id
        """
    ).fetchall()

    updates = []
    unresolved = []
    for row in model_rows:
        capacity, source = resolve_capacity(row["manufacturer"], row["model_name"])
        if capacity is None:
            unresolved.append(
                {
                    "id": row["id"],
                    "manufacturer": row["manufacturer"],
                    "model_name": row["model_name"],
                }
            )
            continue

        current = row["sf6_capacity_kg"]
        if current != capacity:
            conn.execute(
                "UPDATE element_models SET sf6_capacity_kg = ? WHERE id = ?",
                (capacity, row["id"]),
            )
            updates.append(
                {
                    "id": row["id"],
                    "manufacturer": row["manufacturer"],
                    "model_name": row["model_name"],
                    "old_capacity": current,
                    "new_capacity": capacity,
                    "source": source,
                }
            )

    conn.commit()
    after_total = installed_total(conn)
    conn.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "backup_path": str(backup_path),
        "updated_models": len(updates),
        "unresolved_models": len(unresolved),
        "installed_sf6_before": before_total,
        "installed_sf6_after": after_total,
        "model_updates": updates,
        "unresolved": unresolved,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
