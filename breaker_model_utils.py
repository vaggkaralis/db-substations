import math
import re


ELEM_BREAKER_YT = "Διακόπτης ΥΤ"
ELEM_BREAKER_MT = "Διακόπτης ΜΤ"

_BREAKER_VOLTAGE_KV = {
    ELEM_BREAKER_YT: 150.0,
    ELEM_BREAKER_MT: 20.0,
}

_CURRENT_PATTERNS = (
    re.compile(r"\((\d{3,4})\s*(?:A|Α)\)", re.IGNORECASE),
    re.compile(r"(?:^|[^\d])(\d{3,4})\s*(?:A|Α)(?:$|[^\w])", re.IGNORECASE),
)


def get_breaker_nominal_voltage_kv(category):
    return _BREAKER_VOLTAGE_KV.get(str(category or "").strip())


def extract_rated_current_from_model_name(model_name):
    text = str(model_name or "")
    for pattern in _CURRENT_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            try:
                return float(matches[-1])
            except Exception:
                return None
    return None


def calculate_three_phase_power_mva(voltage_kv, current_a):
    if voltage_kv is None or current_a is None:
        return None
    try:
        voltage_val = float(voltage_kv)
        current_val = float(current_a)
    except (TypeError, ValueError):
        return None
    if voltage_val <= 0 or current_val <= 0:
        return None
    return round(math.sqrt(3.0) * voltage_val * current_val / 1000.0, 3)


def infer_breaker_model_values(category, model_name, rated_current_a=None):
    voltage_kv = get_breaker_nominal_voltage_kv(category)
    effective_current = extract_rated_current_from_model_name(model_name)
    if effective_current is None:
        effective_current = rated_current_a
    power_mva = calculate_three_phase_power_mva(voltage_kv, effective_current)
    return effective_current, power_mva
