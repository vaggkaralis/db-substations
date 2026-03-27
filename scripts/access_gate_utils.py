import re
import unicodedata
from collections import defaultdict


# Utility to generate all interconnection gate labels for a list of gate numbers
def generate_interconnection_gate_labels(gate_numbers):
    """
    Given a list of gate numbers (e.g., [1, 2, 3]), return all unique interconnection gate labels.
    Example: [1, 2, 3] -> ['ΠΥΛΗ 1-2', 'ΠΥΛΗ 1-3', 'ΠΥΛΗ 2-3']
    """
    labels = []
    n = len(gate_numbers)
    for i in range(n):
        for j in range(i + 1, n):
            labels.append(f"ΠΥΛΗ {gate_numbers[i]}-{gate_numbers[j]}")
    return labels


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


def extract_breaker_code(value):
    raw = str(value or "").replace("\x00", "").strip().upper()
    raw = unicodedata.normalize("NFD", raw)
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    match = re.search(r"[ΡR]\s*-?\s*(\d+)", raw)
    if not match:
        return None
    return f"Ρ-{int(match.group(1))}"


def parse_substation_gate(full_name):
    parts = [part.strip() for part in str(full_name or "").split(",")]
    if len(parts) < 2:
        return None, None
    try:
        gate_number = int(parts[1])
    except Exception:
        return parts[0], None
    return parts[0], gate_number


def build_access_asset_gate_maps(accdb_path):
    gate_maps = {
        "hv_serial": defaultdict(set),
        "hv_name": defaultdict(set),
        "mv_serial": defaultdict(set),
        "mv_name": defaultdict(set),
        "tx_serial": defaultdict(set),
        "tx_name": defaultdict(set),
    }

    try:
        import pyodbc
    except Exception:
        raise RuntimeError(
            "pyodbc is required to read Access databases; install it or avoid calling this function"
        )

    conn = pyodbc.connect(
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};" + f"DBQ={accdb_path};"
    )
    try:
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM qryAssetBySubstation").fetchall()
    finally:
        conn.close()

    for row in rows:
        substation_name, gate_number = parse_substation_gate(row[0])
        if not substation_name or gate_number is None:
            continue

        norm_substation = normalize_text(substation_name)

        hv_name = extract_breaker_code(row[2])
        hv_serial = normalize_serial(row[3])
        if hv_name:
            gate_maps["hv_name"][(norm_substation, hv_name)].add(gate_number)
            if hv_serial:
                gate_maps["hv_serial"][(norm_substation, hv_name, hv_serial)].add(
                    gate_number
                )

        tx_name = normalize_transformer_name(row[4])
        tx_serial = normalize_serial(row[6])
        if tx_name:
            gate_maps["tx_name"][(norm_substation, tx_name)].add(gate_number)
            if tx_serial:
                gate_maps["tx_serial"][(norm_substation, tx_name, tx_serial)].add(
                    gate_number
                )

        mv_name = extract_breaker_code(row[8])
        mv_serial = normalize_serial(row[9])
        if mv_name:
            gate_maps["mv_name"][(norm_substation, mv_name)].add(gate_number)
            if mv_serial:
                gate_maps["mv_serial"][(norm_substation, mv_name, mv_serial)].add(
                    gate_number
                )

    return gate_maps


def _single_gate(values):
    if not values or len(values) != 1:
        return None
    return next(iter(values))


def find_hv_gate(gate_maps, substation_name, breaker_name, serial_number):
    norm_substation = normalize_text(substation_name)
    breaker_code = extract_breaker_code(breaker_name)
    serial_key = normalize_serial(serial_number)
    if breaker_code and serial_key:
        gate_number = _single_gate(
            gate_maps["hv_serial"].get((norm_substation, breaker_code, serial_key))
        )
        if gate_number is not None:
            return gate_number
    if breaker_code:
        return _single_gate(gate_maps["hv_name"].get((norm_substation, breaker_code)))
    return None


def find_mv_gate(gate_maps, substation_name, breaker_name, serial_number):
    norm_substation = normalize_text(substation_name)
    breaker_code = extract_breaker_code(breaker_name)
    serial_key = normalize_serial(serial_number)
    if breaker_code and serial_key:
        gate_number = _single_gate(
            gate_maps["mv_serial"].get((norm_substation, breaker_code, serial_key))
        )
        if gate_number is not None:
            return gate_number
    if breaker_code:
        return _single_gate(gate_maps["mv_name"].get((norm_substation, breaker_code)))
    return None


def find_transformer_gate(gate_maps, substation_name, transformer_name, serial_number):
    norm_substation = normalize_text(substation_name)
    name_key = normalize_transformer_name(transformer_name)
    serial_key = normalize_serial(serial_number)
    if name_key and serial_key:
        gate_number = _single_gate(
            gate_maps["tx_serial"].get((norm_substation, name_key, serial_key))
        )
        if gate_number is not None:
            return gate_number
    if name_key:
        return _single_gate(gate_maps["tx_name"].get((norm_substation, name_key)))
    return None


def format_gate_label(gate_number, is_interconnection=False):
    if gate_number is None:
        return None
    if is_interconnection:
        return f"ΠΥΛΗ {gate_number}-{gate_number + 1}"
    return f"ΠΥΛΗ {gate_number}"
