import os
import shutil
import tempfile
from datetime import datetime

from openpyxl import load_workbook
from strings_proxy import STRINGS as S


def _safe_float(value):
    if value is None:
        return None
    txt = str(value).strip().replace(",", ".")
    if not txt:
        return None
    try:
        return float(txt)
    except Exception:
        return None


def _safe_date_text(value):
    txt = (value or "").strip()
    if not txt:
        return ""
    try:
        dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return txt


def generate_dga_excel_report(template_path: str, output_path: str, payload: dict) -> str:
    if not os.path.exists(template_path):
        raise FileNotFoundError(
            S["MESSAGES"].get("DGA_TEMPLATE_NOT_FOUND_FMT", "DGA template not found: {path}").format(path=template_path)
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        wb = load_workbook(template_path)
    except PermissionError:
        # OneDrive placeholders or locked files may fail to open directly.
        temp_copy = os.path.join(tempfile.gettempdir(), "dga_template_copy.xlsx")
        shutil.copy2(template_path, temp_copy)
        wb = load_workbook(temp_copy)

    ws = wb["Αναφορά"] if "Αναφορά" in wb.sheetnames else wb[wb.sheetnames[0]]

    # Header section
    ws["B8"] = f"ΥΠΟΣΤΑΘΜΟΣ : {payload.get('substation_name', '')}"
    ws["B9"] = f"ΣΤΟΙΧΕΙΟ ΔΙΚΤΥΟΥ : {payload.get('element_name', '')}"
    ws["B10"] = f"ΚΑΤΑΣΚΕΥΑΣΤΗΣ : {payload.get('manufacturer', '')}"

    ws["I8"] = f"ΣΗΜΕΙΟ ΔΕΙΓΜΑΤΟΛΗΨΙΑΣ : {payload.get('sample_point', '')}"
    ws["I9"] = f"ΑΡΙΘ. ΚΑΤΑΣΚΕΥΑΣΤΗ : {payload.get('serial_number', '')}"
    ws["I10"] = f"ΜΕΘΟΔΟΣ : {payload.get('sampling_method', '')}"

    ws["H13"] = payload.get("sampling_responsible", "")
    ws["H14"] = _safe_date_text(payload.get("sampling_date", ""))
    ws["H15"] = payload.get("measurement_responsible", "")
    ws["H16"] = _safe_date_text(payload.get("measurement_date", ""))
    ws["H17"] = _safe_float(payload.get("sample_temperature"))

    # Gas analysis values
    ws["H19"] = _safe_float(payload.get("h2"))
    ws["H20"] = _safe_float(payload.get("c2h2"))
    ws["H21"] = _safe_float(payload.get("c2h4"))
    ws["H22"] = _safe_float(payload.get("c2h6"))
    ws["H23"] = _safe_float(payload.get("co"))
    ws["H24"] = _safe_float(payload.get("co2"))
    ws["H25"] = _safe_float(payload.get("ch4"))
    ws["H26"] = _safe_float(payload.get("o2"))
    ws["H27"] = _safe_float(payload.get("c3h8"))
    ws["H28"] = _safe_float(payload.get("n2"))
    ws["H29"] = _safe_float(payload.get("h2o"))

    # Physicochemical section
    ws["H39"] = payload.get("sampling_responsible", "")
    ws["H40"] = _safe_date_text(payload.get("sampling_date", ""))
    ws["H41"] = payload.get("measurement_responsible", "")
    ws["H42"] = _safe_date_text(payload.get("measurement_date", ""))
    ws["H43"] = _safe_float(payload.get("sample_temperature"))

    ws["H45"] = _safe_float(payload.get("density"))
    ws["H46"] = _safe_float(payload.get("humidity"))
    ws["H47"] = _safe_float(payload.get("dielectric_strength"))
    ws["H48"] = _safe_float(payload.get("loss_factor"))
    ws["H49"] = _safe_float(payload.get("surface_tension"))

    notes = (payload.get("notes") or "").strip()
    if notes:
        ws["C52"] = notes

    wb.save(output_path)
    return output_path
