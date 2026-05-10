from strings_proxy import STRINGS as S


_RECURRING_MAINTENANCE_TYPE_NORMALIZED = {
    "παραλαβή",
    "επαναληπτική συντήρηση",
    "receipt",
    "recurring maintenance",
}
_LEGACY_RECURRING_MAINTENANCE_TYPE_NORMALIZED = {
    "email",
}
_DGA_MAINTENANCE_TYPE_NORMALIZED = {
    "φυσικοχημικές/αεριοχρωματογραφία",
    "physicochemical/gas chromatography",
}
_FAULT_MAINTENANCE_TYPE_NORMALIZED = {
    "βλάβη",
    "fault",
}
_FAULT_MAINTENANCE_TYPE_FALLBACK_TOKENS = (
    "βλαβ",
    "επισκευ",
    "αποκαταστ",
    "δυσλειτουργ",
    "βραχυκυκλ",
    "αστοχι",
    "fault",
    "failure",
    "repair",
    "restore",
    "outage",
)


def normalize_maintenance_type_value(value):
    return " ".join(str(value or "").split()).casefold()


def get_default_recurring_maintenance_type():
    return S.get("MESSAGES", {}).get("MAINT_TYPE_DEFAULT", "Επαναληπτική συντήρηση")


def canonicalize_maintenance_type(value, default=None):
    normalized = normalize_maintenance_type_value(value)
    if normalized in _LEGACY_RECURRING_MAINTENANCE_TYPE_NORMALIZED:
        return default or get_default_recurring_maintenance_type()
    if value is None or str(value).strip() == "":
        return default
    return value


def is_recurring_maintenance_type(value):
    normalized = normalize_maintenance_type_value(
        canonicalize_maintenance_type(value, value)
    )
    return normalized in _RECURRING_MAINTENANCE_TYPE_NORMALIZED


def is_dga_maintenance_type(value):
    return normalize_maintenance_type_value(value) in _DGA_MAINTENANCE_TYPE_NORMALIZED


def is_fault_maintenance_type(value):
    normalized = normalize_maintenance_type_value(value)
    if normalized in _FAULT_MAINTENANCE_TYPE_NORMALIZED:
        return True
    return any(token in normalized for token in _FAULT_MAINTENANCE_TYPE_FALLBACK_TOKENS)
