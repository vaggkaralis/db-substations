import os
import re
import shutil
import tempfile
from functools import lru_cache
from datetime import datetime

from openpyxl import load_workbook
from strings_proxy import STRINGS as S


_DGA_FIELD_ROWS = [
    ("h2", 19, "gases", "H2"),
    ("c2h2", 20, "gases", "C2H2"),
    ("c2h4", 21, "gases", "C2H4"),
    ("c2h6", 22, "gases", "C2H6"),
    ("co", 23, "gases", "CO"),
    ("co2", 24, "gases", "CO2"),
    ("ch4", 25, "gases", "CH4"),
    ("o2", 26, "gases", "O2"),
    ("c3h8", 27, "gases", "C3H8"),
    ("n2", 28, "gases", "N2"),
    ("h2o", 29, "gases", "H2O"),
    ("density", 45, "physchem", "ΠΥΚΝΟΤΗΤΑ"),
    ("humidity", 46, "physchem", "ΥΓΡΑΣΙΑ"),
    ("dielectric_strength", 47, "physchem", "ΔΙΗΛΕΚΤΡΙΚΗ ΑΝΤΟΧΗ"),
    ("loss_factor", 48, "physchem", "ΣΥΝΤΕΛΕΣΤΗΣ ΑΠΩΛΕΙΩΝ"),
    ("surface_tension", 49, "physchem", "ΔΙΕΠΙΦΑΝΕΙΑΚΗ ΤΑΣΗ"),
]

_GAS_LABEL_OVERRIDES = {
    "h2": "ΥΔΡΟΓΟΝΟ (H2)",
    "c2h2": "ΑΚΕΤΥΛΕΝΙΟ (C2H2)",
    "c2h4": "ΑΙΘΥΛΕΝΙΟ (C2H4)",
    "c2h6": "ΑΙΘΑΝΙΟ (C2H6)",
    "co": "ΜΟΝ.ΑΝΘΡΑΚΑ (CO)",
    "co2": "ΔΙΟΞ. ΑΝΘΡΑΚΑ (CO2)",
    "ch4": "ΜΕΘΑΝΙΟ (CH4)",
    "o2": "ΟΞΥΓΟΝΟ (O2)",
    "c3h8": "ΠΡΟΠΑΝΙΟ (C3H8)",
    "n2": "ΑΖΩΤΟ (N2)",
    "h2o": "ΥΓΡΑΣΙΑ (H2O)",
}

_GAS_LIMIT_OVERRIDES = {
    "h2": "50-150",
    "c2h2": "2-20",
    "c2h4": "60-280",
    "c2h6": "20-90",
    "co": "400-600",
    "co2": "3800-14000",
    "ch4": "30-130",
    "o2": "",
    "c3h8": "",
    "n2": "",
    "h2o": "",
}

# All gas quantities are expressed in ppm.
_GAS_UNIT = "ppm"

_PHYSCHEM_LABEL_OVERRIDES = {
    "density": "ΠΥΚΝΟΤΗΤΑ (DIN 51517)",
    "humidity": "ΥΓΡΑΣΙΑ (IEC 60814)",
    "dielectric_strength": "ΔΙΗΛΕΚΤΡΙΚΗ ΑΝΤΟΧΗ (IEC 156/95)",
    "loss_factor": "ΣΥΝΤΕΛΕΣΤΗΣ ΑΠΩΛΕΙΩΝ (IEC 60247)",
    "surface_tension": "ΔΙΕΠΙΦΑΝΕΙΑΚΗ ΤΑΣΗ (ASTM 971)",
}

_PHYSCHEM_UNIT_OVERRIDES = {
    "density": "g/cm\u00b3",
    "humidity": "ppm",
    "dielectric_strength": "KV",
    "loss_factor": "",
    "surface_tension": "mN/m",
}


def _safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _parse_limit_rule(expr):
    text = _safe_text(expr).replace(" ", "")
    if not text:
        return None
    text = text.replace("−", "-")
    text = text.replace("≤", "<=").replace("≥", ">=")

    if "-" in text and not text.startswith("-"):
        parts = text.split("-", 1)
        left = _safe_float(parts[0])
        right = _safe_float(parts[1])
        if left is not None and right is not None:
            # Accept compact upper bounds like 3800-14 => 3800-14000.
            if left >= 1000 and 0 < right < 100:
                while right < left:
                    right *= 10
            lo, hi = (left, right) if left <= right else (right, left)
            return {
                "raw": _safe_text(expr),
                "min": lo,
                "max": hi,
                "min_inc": True,
                "max_inc": True,
            }

    m = re.match(r"^(<=|>=|<|>)(.+)$", text)
    if m:
        op = m.group(1)
        val = _safe_float(m.group(2))
        if val is None:
            return None
        rule = {
            "raw": _safe_text(expr),
            "min": None,
            "max": None,
            "min_inc": True,
            "max_inc": True,
        }
        if op == "<":
            rule["max"] = val
            rule["max_inc"] = False
        elif op == "<=":
            rule["max"] = val
            rule["max_inc"] = True
        elif op == ">":
            rule["min"] = val
            rule["min_inc"] = False
        else:
            rule["min"] = val
            rule["min_inc"] = True
        return rule

    value = _safe_float(text)
    if value is not None:
        return {
            "raw": _safe_text(expr),
            "min": value,
            "max": value,
            "min_inc": True,
            "max_inc": True,
        }
    return None


def _matches_rule(value, rule):
    if value is None or rule is None:
        return False
    lo = rule.get("min")
    hi = rule.get("max")
    if lo is not None:
        if rule.get("min_inc", True):
            if value < lo:
                return False
        elif value <= lo:
            return False
    if hi is not None:
        if rule.get("max_inc", True):
            if value > hi:
                return False
        elif value >= hi:
            return False
    return True


def _row_limit_rules(ws, section, row):
    if section == "gases":
        good_expr = _safe_text(ws[f"F{row}"].value)
        tolerable_expr = ""
        poor_expr = ""
    else:
        # Columns: K=ΚΑΛΟ, L=ΑΝΕΚΤΟ (optional), N=ΠΤΩΧΟ (optional, skips M).
        good_expr = _safe_text(ws[f"K{row}"].value)
        tolerable_expr = _safe_text(ws[f"L{row}"].value)
        poor_expr = _safe_text(ws[f"N{row}"].value)

    good_rules = []
    tolerable_rules = []
    poor_rules = []

    if good_expr:
        rule = _parse_limit_rule(good_expr)
        if rule:
            good_rules.append(rule)

    if tolerable_expr:
        rule = _parse_limit_rule(tolerable_expr)
        if rule:
            tolerable_rules.append(rule)

    if poor_expr:
        rule = _parse_limit_rule(poor_expr)
        if rule:
            poor_rules.append(rule)

    shown_exprs = [expr for expr in [good_expr, tolerable_expr] if expr]
    combined = good_rules + [r for r in tolerable_rules if r not in good_rules]
    return {
        "good_rules": good_rules,
        "tolerable_rules": tolerable_rules,
        "poor_rules": poor_rules,
        "all_rules": combined,
        "limit_text": " / ".join(shown_exprs),
        "good_text": good_expr,
        "tolerable_text": tolerable_expr,
        "poor_text": poor_expr,
    }


@lru_cache(maxsize=8)
def _load_dga_template_metadata_cached(template_path, mtime):
    try:
        wb = load_workbook(template_path, data_only=True)
    except PermissionError:
        temp_copy = os.path.join(tempfile.gettempdir(), "dga_template_meta_copy.xlsx")
        shutil.copy2(template_path, temp_copy)
        wb = load_workbook(temp_copy, data_only=True)
    ws = wb["Αναφορά"] if "Αναφορά" in wb.sheetnames else wb[wb.sheetnames[0]]

    fields = []
    by_key = {}

    for key, row, section, fallback_label in _DGA_FIELD_ROWS:
        label = _safe_text(ws[f"B{row}"].value) or fallback_label
        if section == "gases":
            label = _GAS_LABEL_OVERRIDES.get(key, label)
        elif section == "physchem":
            label = _PHYSCHEM_LABEL_OVERRIDES.get(key, label)
        unit = _safe_text(ws[f"F{row}"].value)
        if section == "gases":
            unit = _GAS_UNIT
        elif key in _PHYSCHEM_UNIT_OVERRIDES:
            unit = _PHYSCHEM_UNIT_OVERRIDES[key]
        if section == "gases":
            gas_expr = _GAS_LIMIT_OVERRIDES.get(key, "")
            gas_rule = _parse_limit_rule(gas_expr) if gas_expr else None
            rule_info = {
                "good_rules": [gas_rule] if gas_rule else [],
                "tolerable_rules": [],
                "all_rules": [gas_rule] if gas_rule else [],
                "limit_text": gas_expr,
                "good_text": gas_expr,
                "tolerable_text": "",
            }
        else:
            rule_info = _row_limit_rules(ws, section, row)
        field = {
            "key": key,
            "row": row,
            "section": section,
            "label": label,
            "unit": unit,
            "rules": rule_info.get("all_rules") or [],
            "good_rules": rule_info.get("good_rules") or [],
            "tolerable_rules": rule_info.get("tolerable_rules") or [],
            "poor_rules": rule_info.get("poor_rules") or [],
            "limit_text": rule_info.get("limit_text") or "",
            "good_text": rule_info.get("good_text") or "",
            "tolerable_text": rule_info.get("tolerable_text") or "",
            "poor_text": rule_info.get("poor_text") or "",
        }
        fields.append(field)
        by_key[key] = field

    return {
        "sections": {
            "meta": "Στοιχεία Δειγματοληψίας / Μέτρησης",
            "gases": _safe_text(ws["B18"].value) or "Αέρια",
            "physchem": _safe_text(ws["F38"].value) or "Φυσικοχημικές Μετρήσεις",
        },
        "fields": fields,
        "by_key": by_key,
    }


def load_dga_template_metadata(template_path):
    """Return field labels, categories and limit rules from the DGA template."""
    try:
        path = os.path.abspath(template_path)
        mtime = os.path.getmtime(path)
        return _load_dga_template_metadata_cached(path, mtime)
    except Exception:
        fallback = {
            "sections": {
                "meta": "Στοιχεία Δειγματοληψίας / Μέτρησης",
                "gases": "Αέρια",
                "physchem": "Φυσικοχημικές Μετρήσεις",
            },
            "fields": [],
            "by_key": {},
        }
        for key, row, section, label in _DGA_FIELD_ROWS:
            field = {
                "key": key,
                "row": row,
                "section": section,
                "label": label,
                "unit": "",
                "rules": [],
                "good_rules": [],
                "tolerable_rules": [],
                "poor_rules": [],
                "limit_text": "",
                "good_text": "",
                "tolerable_text": "",
                "poor_text": "",
            }
            fallback["fields"].append(field)
            fallback["by_key"][key] = field
        return fallback


def evaluate_dga_limits(values, template_path):
    """Evaluate one DGA measurement dict and return ok/warn/bad details."""
    metadata = load_dga_template_metadata(template_path)
    problems = []
    warnings = []
    checks = []

    for field in metadata.get("fields", []):
        rules = field.get("rules") or []
        if not rules:
            continue
        raw = values.get(field["key"])
        value = _safe_float(raw)
        if value is None:
            continue

        good_rules = field.get("good_rules") or []
        tolerable_rules = field.get("tolerable_rules") or []

        is_good = bool(good_rules) and any(_matches_rule(value, rule) for rule in good_rules)
        is_tolerable = bool(tolerable_rules) and any(
            _matches_rule(value, rule) for rule in tolerable_rules
        )
        is_allowed = any(_matches_rule(value, rule) for rule in rules)

        level = "bad"
        if is_good:
            level = "ok"
        elif is_tolerable:
            level = "warn"
        elif not good_rules and is_allowed:
            # Fields with only one limit column (e.g. gases) are either ok or bad.
            level = "ok"

        item = {
            "key": field["key"],
            "label": field.get("label") or field["key"],
            "value": value,
            "limit_text": field.get("limit_text") or "",
            "good_text": field.get("good_text") or "",
            "tolerable_text": field.get("tolerable_text") or "",
            "poor_text": field.get("poor_text") or "",
            "section": field.get("section") or "",
            "level": level,
        }
        checks.append(item)

        if level == "warn":
            warnings.append(item)
        elif level == "bad":
            problems.append(item)

    overall = "ok"
    if problems:
        overall = "bad"
    elif warnings:
        overall = "warn"

    return {
        "is_problematic": bool(problems),
        "has_warnings": bool(warnings),
        "overall_level": overall,
        "checks": checks,
        "warnings": warnings,
        "problems": problems,
        "metadata": metadata,
    }


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


def _surname_upper(value):
    txt = (value or "").strip()
    if not txt:
        return ""
    parts = txt.split()
    return (parts[-1] if parts else txt).upper()


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

    ws["H13"] = _surname_upper(payload.get("sampling_responsible", ""))
    ws["H14"] = _safe_date_text(payload.get("sampling_date", ""))
    ws["H15"] = _surname_upper(payload.get("measurement_responsible", ""))
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
    ws["H39"] = _surname_upper(payload.get("sampling_responsible", ""))
    ws["H40"] = _safe_date_text(payload.get("sampling_date", ""))
    ws["H41"] = _surname_upper(payload.get("measurement_responsible", ""))
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
